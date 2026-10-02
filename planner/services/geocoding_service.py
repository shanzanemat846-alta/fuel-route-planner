"""
Turns user input into a Location. Tried in this order:
"lat,lng" -> "City, ST" from the local cities table -> Nominatim (only for full addresses).
"""
import difflib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from planner.constants import (
    CACHE_PREFIX_GEOCODE,
    CANADIAN_PROVINCE_CODES,
    CITY_FUZZY_MATCH_CUTOFF,
    GEOCODE_CACHE_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    NOMINATIM_COUNTRY_CODE,
    NON_US_REGION_NAMES,
)
from planner.dtos import Location
from planner.exceptions import (
    ExternalServiceError,
    InvalidLocationError,
    LocationNotFoundError,
    LocationOutsideUSAError,
)
from planner.helpers.cache_keys import make_cache_key
from planner.helpers.geo import is_within_usa
from planner.helpers.text import (
    US_STATE_CODES,
    looks_like_coordinates,
    parse_city_state,
    parse_coordinates,
    trailing_region,
)
from planner.models import City
from planner.services.http_client import get_http_session

logger = logging.getLogger(__name__)


class GeocodingService:
    def resolve(self, query: str) -> Location:
        query = (query or "").strip()
        self._reject_non_us_region(query)
        location = (
            self._from_coordinates(query)
            or self._from_local_cities(query)
            or self._from_nominatim(query)
        )
        if not is_within_usa(location.latitude, location.longitude):
            raise LocationOutsideUSAError(f"'{query}' is outside the USA.")
        return location

    @staticmethod
    def _reject_non_us_region(query: str) -> None:
        # Has to run before Nominatim, otherwise "Toronto, ON" comes back as
        # "Toronto Court, Indianapolis" because we restrict the search to the US.
        region = trailing_region(query)
        if region is None:
            return
        if region.upper() in CANADIAN_PROVINCE_CODES or region.lower() in NON_US_REGION_NAMES:
            raise LocationOutsideUSAError(f"'{query}' is outside the USA.")
        if len(region) == 2 and region.upper() not in US_STATE_CODES:
            raise LocationNotFoundError(f"'{region}' in '{query}' is not a US state code.")

    @staticmethod
    def _from_coordinates(query: str) -> Location | None:
        if not looks_like_coordinates(query):
            return None
        coords = parse_coordinates(query)
        if coords is None:
            # without this Nominatim reads "100,200" as a street address
            raise InvalidLocationError(
                f"'{query}' is not a valid 'lat,lng' pair (latitude -90..90, longitude -180..180)."
            )
        lat, lng = coords
        return Location(query=query, label=f"{lat:.5f}, {lng:.5f}", latitude=lat, longitude=lng, source="coordinates")

    @staticmethod
    def _from_local_cities(query: str) -> Location | None:
        parsed = parse_city_state(query)
        if parsed is None:
            return None
        city_name, state_code = parsed
        city = City.objects.filter(state_code=state_code, normalized_name=city_name).first()
        if city is None:
            # small typos like "Sacremento, CA"
            names = list(City.objects.filter(state_code=state_code).values_list("normalized_name", flat=True))
            match = difflib.get_close_matches(city_name, names, n=1, cutoff=CITY_FUZZY_MATCH_CUTOFF)
            if match:
                city = City.objects.filter(state_code=state_code, normalized_name=match[0]).first()
        if city is None:
            return None
        return Location(
            query=query,
            label=f"{city.name}, {city.state_code}",
            latitude=city.latitude,
            longitude=city.longitude,
            source="local_city_db",
        )

    @staticmethod
    def _from_nominatim(query: str) -> Location:
        cache_key = make_cache_key(CACHE_PREFIX_GEOCODE, query)
        cached = cache.get(cache_key)
        if cached:
            return cached

        logger.info("Geocoding via Nominatim: %s", query)
        try:
            response = get_http_session().get(
                f"{settings.NOMINATIM_BASE_URL}/search",
                params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": NOMINATIM_COUNTRY_CODE},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            results = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExternalServiceError("Geocoding service is unavailable, try 'City, ST' or 'lat,lng'.") from exc

        if not results:
            raise LocationNotFoundError(f"Could not find a US location for '{query}'.")
        top = results[0]
        location = Location(
            query=query,
            label=top.get("display_name", query),
            latitude=float(top["lat"]),
            longitude=float(top["lon"]),
            source="nominatim",
        )
        cache.set(cache_key, location, GEOCODE_CACHE_TIMEOUT_SECONDS)
        return location
