import numpy as np
from django.core.cache import cache
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from planner.constants import PLAN_CACHE_TIMEOUT_SECONDS
from planner.dtos import Route
from planner.exceptions import PlannerError, StationDataNotLoadedError
from planner.models import FuelStation
from planner.serializers import RoutePlanRequestSerializer
from planner.services.route_planner import RoutePlannerService
from planner.services.station_index import StationIndex

CACHE_KEY_STATION_NAMES = "map-station-names"


class RoutePlanController(APIView):
    """
    GET  /api/v1/route/?start=New York, NY&finish=Los Angeles, CA
    POST /api/v1/route/  {"start": "...", "finish": "...", "include_geometry": true}
    """

    def get(self, request: Request) -> Response:
        return self._plan(request.query_params)

    def post(self, request: Request) -> Response:
        return self._plan(request.data)

    @staticmethod
    def _plan(data) -> Response:
        serializer = RoutePlanRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        payload = RoutePlannerService().plan(**serializer.validated_data)
        return Response(payload, status=status.HTTP_200_OK)


class RouteMapController(View):
    """
    GET /api/v1/route/map/?start=...&finish=...

    Same plan as the API, shown on a Leaflet map with a form for a new trip.
    """

    template_name = "planner/route_map.html"

    def get(self, request):
        context = {
            "start": request.GET.get("start", ""),
            "finish": request.GET.get("finish", ""),
            "examples": EXAMPLE_TRIPS,
        }
        if not request.GET.get("start") and not request.GET.get("finish"):
            return render(request, self.template_name, {**context, "stations": _map_stations(None)})

        serializer = RoutePlanRequestSerializer(data=request.GET)
        if not serializer.is_valid():
            return self._error(request, context, _readable_errors(serializer.errors), 400)
        try:
            plan = RoutePlannerService().plan(**{**serializer.validated_data, "include_geometry": True})
        except PlannerError as exc:
            return self._error(request, context, exc.message, exc.status_code)
        return render(request, self.template_name, {**context, "plan": plan, "stations": _map_stations(plan)})

    def _error(self, request, context: dict, message: str, status_code: int):
        return render(
            request, self.template_name, {**context, "error": message, "stations": _map_stations(None)}, status=status_code
        )


EXAMPLE_TRIPS = [
    {"start": start, "finish": finish, "label": f"{start.split(',')[0]} → {finish.split(',')[0]}"}
    for start, finish in [
        ("New York, NY", "Los Angeles, CA"),
        ("Chicago, IL", "Dallas, TX"),
        ("Seattle, WA", "Miami, FL"),
        ("Denver, CO", "Salt Lake City, UT"),
        ("Houston, TX", "Austin, TX"),
    ]
]


def _readable_errors(errors: dict) -> str:
    lines = []
    for field, messages in errors.items():
        prefix = "" if field == "non_field_errors" else f"{field}: "
        lines += [f"{prefix}{message}" for message in messages]
    return " ".join(lines)


def _map_stations(plan: dict | None) -> list[list]:
    """
    Rows of [lat, lng, price, name, city, state, route_mile] for the map.
    route_mile is only set for stations along the route, so the map can colour them.
    """
    try:
        index = StationIndex.instance()
    except StationDataNotLoadedError:
        return []
    route_miles = {}
    if plan is not None:
        line = next(f for f in plan["geojson"]["features"] if f["properties"]["kind"] == "route")
        route = Route(
            coordinates=np.array([[lat, lng] for lng, lat in line["geometry"]["coordinates"]]),
            distance_miles=plan["route"]["distance_miles"],
            duration_seconds=0.0,
        )
        corridor = plan["meta"]["station_corridor_miles"]
        route_miles = {s.station_index: round(s.route_mile, 1) for s in index.stations_along_route(route, corridor)}

    names = _station_names()
    return [
        [
            round(float(index.latitudes[i]), 4),
            round(float(index.longitudes[i]), 4),
            round(float(index.prices[i]), 3),
            *names.get(int(db_id), ("", "", "")),
            route_miles.get(i),
        ]
        for i, db_id in enumerate(index.db_ids)
    ]


def _station_names() -> dict[int, tuple[str, str, str]]:
    names = cache.get(CACHE_KEY_STATION_NAMES)
    if names is None:
        names = {pk: (name, city, state) for pk, name, city, state in FuelStation.objects.values_list("id", "name", "city", "state")}
        cache.set(CACHE_KEY_STATION_NAMES, names, PLAN_CACHE_TIMEOUT_SECONDS)
    return names
