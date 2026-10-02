"""
Runs a full request: geocode -> OSRM route -> stations near the route ->
optimizer -> response payload. The payload is cached per start/finish.
"""
import logging
import time

from django.core.cache import cache
from django.urls import reverse
from django.utils.http import urlencode

from planner.constants import (
    CACHE_PREFIX_PLAN,
    PLAN_CACHE_TIMEOUT_SECONDS,
    RESPONSE_GEOMETRY_MAX_POINTS,
    SAME_LOCATION_MILES,
    SECONDS_PER_HOUR,
    START_WITH_FULL_TANK,
    STATION_CORRIDOR_MILES_STEPS,
    VEHICLE_MAX_RANGE_MILES,
    VEHICLE_MILES_PER_GALLON,
)
from planner.dtos import FuelPlan, Location, Route
from planner.exceptions import NoFeasibleFuelPlanError, SameLocationError
from planner.helpers.cache_keys import make_cache_key
from planner.helpers.geo import downsample_evenly, haversine_miles
from planner.models import FuelStation
from planner.services.fuel_optimizer import optimize_fuel_stops
from planner.services.geocoding_service import GeocodingService
from planner.services.routing_service import RoutingService
from planner.services.station_index import StationIndex

logger = logging.getLogger(__name__)


class RoutePlannerService:
    def __init__(
        self,
        geocoder: GeocodingService | None = None,
        router: RoutingService | None = None,
    ) -> None:
        # passed in by the tests (FakeRouter)
        self.geocoder = geocoder or GeocodingService()
        self.router = router or RoutingService()

    def plan(self, start: str, finish: str, include_geometry: bool = True) -> dict:
        cache_key = make_cache_key(CACHE_PREFIX_PLAN, start, finish, include_geometry)
        cached = cache.get(cache_key)
        if cached is not None:
            return {**cached, "meta": {**cached["meta"], "cached": True}}

        started = time.perf_counter()
        start_location = self.geocoder.resolve(start)
        finish_location = self.geocoder.resolve(finish)
        self._ensure_different_places(start_location, finish_location)
        route = self.router.get_route(start_location, finish_location)
        plan, corridor = self._optimise_with_widening_corridor(route)

        payload = self._build_payload(start_location, finish_location, route, plan, corridor, include_geometry)
        payload["meta"]["compute_time_ms"] = round((time.perf_counter() - started) * 1000, 1)
        cache.set(cache_key, payload, PLAN_CACHE_TIMEOUT_SECONDS)
        return payload

    @staticmethod
    def _ensure_different_places(start: Location, finish: Location) -> None:
        # the serializer only compares the text, "Chicago, IL" and "chicago,IL" get past it
        if haversine_miles(start.latitude, start.longitude, finish.latitude, finish.longitude) < SAME_LOCATION_MILES:
            raise SameLocationError(
                f"Start '{start.query}' and finish '{finish.query}' are the same location ({start.label})."
            )

    @staticmethod
    def _optimise_with_widening_corridor(route: Route) -> tuple[FuelPlan, float]:
        index = StationIndex.instance()
        last_error: NoFeasibleFuelPlanError | None = None
        for corridor in STATION_CORRIDOR_MILES_STEPS:
            candidates = index.stations_along_route(route, corridor)
            try:
                plan = optimize_fuel_stops(
                    candidates,
                    total_miles=route.distance_miles,
                    max_range_miles=VEHICLE_MAX_RANGE_MILES,
                    miles_per_gallon=VEHICLE_MILES_PER_GALLON,
                    start_with_full_tank=START_WITH_FULL_TANK,
                )
                logger.info("Plan found with %d candidates in %.0f mi corridor", len(candidates), corridor)
                return plan, corridor
            except NoFeasibleFuelPlanError as exc:
                last_error = exc
        widest = STATION_CORRIDOR_MILES_STEPS[-1]
        raise NoFeasibleFuelPlanError(
            f"{last_error.message} Searched up to {widest:.0f} miles either side of the route."  # type: ignore[union-attr]
        )

    def _build_payload(
        self,
        start: Location,
        finish: Location,
        route: Route,
        plan: FuelPlan,
        corridor: float,
        include_geometry: bool,
    ) -> dict:
        index = StationIndex.instance()
        stop_db_ids = [int(index.db_ids[s.station.station_index]) for s in plan.stops]
        stations_by_id = FuelStation.objects.in_bulk(stop_db_ids)

        fuel_stops = []
        for sequence, (stop, db_id) in enumerate(zip(plan.stops, stop_db_ids), start=1):
            station = stations_by_id[db_id]
            price = float(station.retail_price)
            fuel_stops.append(
                {
                    "sequence": sequence,
                    "opis_id": station.opis_id,
                    "name": station.name,
                    "address": station.address,
                    "city": station.city,
                    "state": station.state,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "price_per_gallon": round(price, 3),
                    "mile_marker": round(stop.station.route_mile, 1),
                    "distance_from_route_miles": round(stop.station.offset_miles, 1),
                    "gallons": round(stop.gallons, 2),
                    "cost": round(stop.cost, 2),
                    "detour": self._detour(stop.station.offset_miles, price),
                }
            )
        detour_miles = sum(2 * stop.station.offset_miles for stop in plan.stops)
        detour_cost = sum(2 * s.station.offset_miles / VEHICLE_MILES_PER_GALLON * s.station.price for s in plan.stops)

        payload = {
            "start": self._location_payload(start),
            "finish": self._location_payload(finish),
            "route": {
                "distance_miles": round(route.distance_miles, 1),
                "duration_hours": round(route.duration_seconds / SECONDS_PER_HOUR, 2),
            },
            "fuel_stops": fuel_stops,
            "summary": {
                "total_fuel_cost": round(plan.total_cost, 2),
                "total_gallons": round(plan.total_gallons, 2),
                "number_of_stops": len(fuel_stops),
                "average_price_per_gallon": (
                    round(plan.total_cost / plan.total_gallons, 3) if plan.total_gallons else 0.0
                ),
                "vehicle_range_miles": VEHICLE_MAX_RANGE_MILES,
                "vehicle_mpg": VEHICLE_MILES_PER_GALLON,
                "starts_with_full_tank": START_WITH_FULL_TANK,
            },
            # extra info only, not part of total_fuel_cost
            "detour_estimate": {
                "round_trip_miles": round(detour_miles, 1),
                "gallons": round(detour_miles / VEHICLE_MILES_PER_GALLON, 2),
                "cost": round(detour_cost, 2),
                "total_fuel_cost_with_detours": round(plan.total_cost + detour_cost, 2),
                "note": "Straight-line estimate of driving from the route to each stop and back. "
                "Not included in total_fuel_cost.",
            },
            "map_url": f"{reverse('planner:route-map')}?{urlencode({'start': start.query, 'finish': finish.query})}",
            "meta": {"station_corridor_miles": corridor, "cached": False},
        }
        if include_geometry:
            payload["geojson"] = self._geojson(route, fuel_stops, start, finish)
        return payload

    @staticmethod
    def _detour(offset_miles: float, price: float) -> dict:
        # Driving off the route to the station and back. Straight line from the
        # city centre, so only a rough estimate. Priced at the station's own price.
        round_trip = 2 * offset_miles
        gallons = round_trip / VEHICLE_MILES_PER_GALLON
        return {
            "one_way_miles": round(offset_miles, 1),
            "round_trip_miles": round(round_trip, 1),
            "gallons": round(gallons, 2),
            "cost": round(gallons * price, 2),
        }

    @staticmethod
    def _location_payload(location: Location) -> dict:
        return {
            "query": location.query,
            "label": location.label,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "resolved_by": location.source,
        }

    @staticmethod
    def _geojson(route: Route, fuel_stops: list[dict], start: Location, finish: Location) -> dict:
        line = [[round(lng, 5), round(lat, 5)] for lat, lng in route.coordinates.tolist()]
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": downsample_evenly(line, RESPONSE_GEOMETRY_MAX_POINTS)},
                "properties": {"kind": "route"},
            },
            _point_feature(start.longitude, start.latitude, {"kind": "start", "label": start.label}),
            _point_feature(finish.longitude, finish.latitude, {"kind": "finish", "label": finish.label}),
        ]
        features += [
            _point_feature(s["longitude"], s["latitude"], {"kind": "fuel_stop", **s}) for s in fuel_stops
        ]
        return {"type": "FeatureCollection", "features": features}


def _point_feature(lng: float, lat: float, properties: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": properties}
