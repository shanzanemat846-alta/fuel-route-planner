"""Driving route from the public OSRM server. This is the only external call per request (cached)."""
import logging

import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache

from planner.constants import (
    CACHE_PREFIX_ROUTE,
    HTTP_TIMEOUT_SECONDS,
    METERS_PER_MILE,
    OSRM_PROFILE,
    ROUTE_CACHE_TIMEOUT_SECONDS,
)
from planner.dtos import Location, Route
from planner.exceptions import ExternalServiceError, RouteNotFoundError
from planner.helpers.cache_keys import make_cache_key
from planner.services.http_client import get_http_session

logger = logging.getLogger(__name__)


class RoutingService:
    def get_route(self, start: Location, finish: Location) -> Route:
        cache_key = make_cache_key(
            CACHE_PREFIX_ROUTE,
            f"{start.latitude:.5f},{start.longitude:.5f}",
            f"{finish.latitude:.5f},{finish.longitude:.5f}",
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        route = self._fetch_route(start, finish)
        cache.set(cache_key, route, ROUTE_CACHE_TIMEOUT_SECONDS)
        return route

    @staticmethod
    def _fetch_route(start: Location, finish: Location) -> Route:
        # OSRM wants lng,lat
        waypoints = f"{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}"
        url = f"{settings.OSRM_BASE_URL}/route/v1/{OSRM_PROFILE}/{waypoints}"
        params = {"overview": "full", "geometries": "geojson", "steps": "false", "alternatives": "false"}

        logger.info("Requesting route from OSRM: %s -> %s", start.label, finish.label)
        try:
            response = get_http_session().get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExternalServiceError("Routing service is unavailable, please retry.") from exc

        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RouteNotFoundError(
                f"No drivable route between '{start.label}' and '{finish.label}' "
                f"({payload.get('message') or payload.get('code')})."
            )

        best = payload["routes"][0]
        lng_lat = np.asarray(best["geometry"]["coordinates"], dtype=float)
        return Route(
            coordinates=lng_lat[:, ::-1].copy(),  # back to [lat, lng]
            distance_miles=float(best["distance"]) / METERS_PER_MILE,
            duration_seconds=float(best["duration"]),
        )
