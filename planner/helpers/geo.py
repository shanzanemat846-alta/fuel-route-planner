"""Geo helpers (numpy). Coordinates are (lat, lng) in degrees unless noted."""
import json
import math
from functools import lru_cache

import numpy as np

from planner.constants import EARTH_RADIUS_MILES, USA_BOUNDARY_FILE, USA_BOUNDING_BOXES, USA_COAST_TOLERANCE_MILES


def haversine_miles(lat1, lng1, lat2, lng2):
    """Great-circle distance in miles. Works on scalars or numpy arrays."""
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def cumulative_distances_miles(coords: np.ndarray) -> np.ndarray:
    """Distance from the first point to every point of a [lat, lng] polyline."""
    if len(coords) < 2:
        return np.zeros(len(coords))
    segment = haversine_miles(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])
    return np.concatenate(([0.0], np.cumsum(segment)))


def resample_indices(cumulative: np.ndarray, spacing_miles: float) -> np.ndarray:
    """Indices of points roughly `spacing_miles` apart (first and last always kept)."""
    if len(cumulative) == 0:
        return np.array([], dtype=int)
    targets = np.arange(0.0, cumulative[-1], spacing_miles)
    idx = np.searchsorted(cumulative, targets)
    idx = np.unique(np.concatenate((idx, [len(cumulative) - 1])))
    return idx


def to_unit_vectors(lat, lng) -> np.ndarray:
    """lat/lng -> (x, y, z) on the unit sphere, so a KD-tree can be used."""
    lat, lng = np.radians(lat), np.radians(lng)
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lng), cos_lat * np.sin(lng), np.sin(lat)))


def miles_to_chord(miles: float) -> float:
    return 2.0 * np.sin(miles / (2.0 * EARTH_RADIUS_MILES))


def chord_to_miles(chord):
    return 2.0 * EARTH_RADIUS_MILES * np.arcsin(np.clip(np.asarray(chord) / 2.0, 0.0, 1.0))


def downsample_evenly(points: list, max_points: int) -> list:
    if len(points) <= max_points:
        return points
    step = len(points) / (max_points - 1)
    sampled = [points[int(i * step)] for i in range(max_points - 1)]
    sampled.append(points[-1])
    return sampled


def is_within_usa(lat: float, lng: float) -> bool:
    """
    Contiguous US or Alaska. Point-in-polygon against the state outlines, plus a
    small margin for coastal points. The margin has to stay under ~1 mile or
    border towns like Windsor (Canada) would pass as Detroit.
    """
    in_box = any(
        min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
        for min_lat, max_lat, min_lng, max_lng in USA_BOUNDING_BOXES
    )
    if not in_box:
        return False
    rings = _nearby_rings(lat, lng, margin_degrees=0.0)
    if any(_point_in_ring(lat, lng, ring) for ring in rings):
        return True
    return _distance_to_rings_miles(lat, lng, _nearby_rings(lat, lng, margin_degrees=0.05)) <= USA_COAST_TOLERANCE_MILES


@lru_cache(maxsize=1)
def _usa_rings() -> tuple[tuple[np.ndarray, tuple[float, float, float, float]], ...]:
    # [(ring as [lng, lat] array, (min_lng, max_lng, min_lat, max_lat)), ...]
    with open(USA_BOUNDARY_FILE) as fh:
        raw = json.load(fh)["rings"]
    rings = []
    for ring in raw:
        arr = np.asarray(ring, dtype=float)
        rings.append((arr, (arr[:, 0].min(), arr[:, 0].max(), arr[:, 1].min(), arr[:, 1].max())))
    return tuple(rings)


def _nearby_rings(lat: float, lng: float, margin_degrees: float) -> list[np.ndarray]:
    return [
        ring
        for ring, (min_lng, max_lng, min_lat, max_lat) in _usa_rings()
        if min_lng - margin_degrees <= lng <= max_lng + margin_degrees
        and min_lat - margin_degrees <= lat <= max_lat + margin_degrees
    ]


def _point_in_ring(lat: float, lng: float, ring: np.ndarray) -> bool:
    # ray casting (even-odd rule)
    x, y = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    straddles = (y > lat) != (y2 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_cross = x + (lat - y) * (x2 - x) / (y2 - y)
    return bool(np.count_nonzero(straddles & (lng < x_cross)) % 2)


def _distance_to_rings_miles(lat: float, lng: float, rings: list[np.ndarray]) -> float:
    # flat projection around the point - good enough for the small distances we care about
    best = math.inf
    scale = np.array([math.cos(math.radians(lat)), 1.0]) * (EARTH_RADIUS_MILES * math.pi / 180)
    point = np.array([lng, lat])
    for ring in rings:
        a, b = ring[:-1], ring[1:]
        ab, ap = (b - a) * scale, (point - a) * scale
        t = np.clip((ap * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-12), 0.0, 1.0)
        best = min(best, float(np.linalg.norm(ap - ab * t[:, None], axis=1).min()))
    return best
