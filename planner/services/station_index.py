"""
All stations kept in memory as numpy arrays (loaded once per process).

For each route we build a KD-tree over the route points and query every
station against it in one call. Takes a few ms even for coast to coast.
"""
import logging
import threading

import numpy as np
from scipy.spatial import cKDTree

from planner.constants import ROUTE_SAMPLE_SPACING_MILES
from planner.dtos import Route, StationOnRoute
from planner.exceptions import StationDataNotLoadedError
from planner.helpers.geo import (
    chord_to_miles,
    cumulative_distances_miles,
    miles_to_chord,
    resample_indices,
    to_unit_vectors,
)
from planner.models import FuelStation

logger = logging.getLogger(__name__)


class StationIndex:
    """Use StationIndex.instance(), it is built on first use."""

    _instance: "StationIndex | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        rows = list(
            FuelStation.objects.values_list(
                "id", "opis_id", "retail_price", "latitude", "longitude"
            ).order_by("id")
        )
        if not rows:
            raise StationDataNotLoadedError(
                "No fuel stations loaded. Run `python manage.py load_fuel_stations` first."
            )
        self.db_ids = np.array([r[0] for r in rows], dtype=np.int64)
        self.opis_ids = np.array([r[1] for r in rows], dtype=np.int64)
        self.prices = np.array([float(r[2]) for r in rows], dtype=float)
        self.latitudes = np.array([r[3] for r in rows], dtype=float)
        self.longitudes = np.array([r[4] for r in rows], dtype=float)
        self.unit_vectors = to_unit_vectors(self.latitudes, self.longitudes)
        logger.info("Station index built with %d stations", len(rows))

    @classmethod
    def instance(cls) -> "StationIndex":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def invalidate(cls) -> None:
        # call after reloading the stations
        with cls._lock:
            cls._instance = None

    def stations_along_route(self, route: Route, corridor_miles: float) -> list[StationOnRoute]:
        """Stations within `corridor_miles` of the route, sorted by how far along the route they are."""
        cumulative = cumulative_distances_miles(route.coordinates)
        if cumulative[-1] <= 0:
            return []
        # scale to OSRM's distance so mile markers match the route total
        cumulative = cumulative * (route.distance_miles / cumulative[-1])

        sample_idx = resample_indices(cumulative, ROUTE_SAMPLE_SPACING_MILES)
        samples = route.coordinates[sample_idx]
        sample_miles = cumulative[sample_idx]

        tree = cKDTree(to_unit_vectors(samples[:, 0], samples[:, 1]))
        chord, nearest = tree.query(
            self.unit_vectors, k=1, distance_upper_bound=miles_to_chord(corridor_miles)
        )
        hits = np.flatnonzero(np.isfinite(chord))

        stations = [
            StationOnRoute(
                station_index=int(i),
                opis_id=int(self.opis_ids[i]),
                price=float(self.prices[i]),
                route_mile=float(sample_miles[nearest[i]]),
                offset_miles=float(chord_to_miles(chord[i])),
            )
            for i in hits
        ]
        stations.sort(key=lambda s: (s.route_mile, s.price))
        return stations
