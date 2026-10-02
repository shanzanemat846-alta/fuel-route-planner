from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Location:
    query: str
    label: str
    latitude: float
    longitude: float
    source: str  # coordinates / local_city_db / nominatim


@dataclass(frozen=True)
class Route:
    coordinates: np.ndarray = field(repr=False)  # (n, 2) array of [lat, lng]
    distance_miles: float
    duration_seconds: float


@dataclass(frozen=True)
class StationOnRoute:
    station_index: int  # position in the StationIndex arrays
    opis_id: int
    price: float
    route_mile: float  # miles from the start, along the route
    offset_miles: float  # how far the station is from the route


@dataclass(frozen=True)
class FuelStop:
    station: StationOnRoute
    gallons: float
    cost: float


@dataclass(frozen=True)
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: float
