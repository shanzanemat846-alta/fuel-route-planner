"""Test helpers: tiny data builders and a fake routing service (no network)."""
from decimal import Decimal

import numpy as np

from planner.dtos import Location, Route, StationOnRoute
from planner.helpers.geo import cumulative_distances_miles
from planner.models import City, FuelStation


def station(mile: float, price: float, idx: int = 0, offset: float = 0.0) -> StationOnRoute:
    return StationOnRoute(station_index=idx, opis_id=idx, price=price, route_mile=mile, offset_miles=offset)


def straight_route(start: tuple[float, float], finish: tuple[float, float], points: int = 2000) -> Route:
    coords = np.column_stack(
        (np.linspace(start[0], finish[0], points), np.linspace(start[1], finish[1], points))
    )
    return Route(coordinates=coords, distance_miles=float(cumulative_distances_miles(coords)[-1]), duration_seconds=3600)


class FakeRouter:
    """Stands in for OSRM: returns a straight line and counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    def get_route(self, start: Location, finish: Location) -> Route:
        self.calls += 1
        return straight_route((start.latitude, start.longitude), (finish.latitude, finish.longitude))


def make_city(name: str, state: str, lat: float, lng: float) -> City:
    from planner.helpers.text import normalize_city_name

    return City.objects.create(
        name=name, normalized_name=normalize_city_name(name), state_code=state, state_name=state,
        latitude=lat, longitude=lng,
    )


def make_station(opis_id: int, price: str, lat: float, lng: float, city: str = "Town", state: str = "IL") -> FuelStation:
    return FuelStation.objects.create(
        opis_id=opis_id, name=f"Stop {opis_id}", address="I-80", city=city, state=state,
        retail_price=Decimal(price), latitude=lat, longitude=lng,
    )
