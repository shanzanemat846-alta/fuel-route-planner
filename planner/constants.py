"""Assumptions and tunable values used across the planner."""
from pathlib import Path

from django.conf import settings

# Vehicle (given in the assignment)
VEHICLE_MAX_RANGE_MILES: float = 500.0
VEHICLE_MILES_PER_GALLON: float = 10.0

# Empty tank at the start means the total covers all the fuel for the trip.
# Set to True to assume a full tank and only count fuel bought on the way.
START_WITH_FULL_TANK: bool = False

# Units
EARTH_RADIUS_MILES: float = 3958.7613
METERS_PER_MILE: float = 1609.344
SECONDS_PER_HOUR: int = 3600

# Station search
# Stations are placed at their city centre, so they are usually a few miles
# off the highway. Start with a narrow corridor and widen it only when the
# trip can't be completed (sparse areas).
STATION_CORRIDOR_MILES_STEPS: tuple[float, ...] = (10.0, 25.0, 50.0)

ROUTE_SAMPLE_SPACING_MILES: float = 0.5

# keeps the geojson in the response small
RESPONSE_GEOMETRY_MAX_POINTS: int = 2000

# Data files
DATA_DIR: Path = Path(settings.BASE_DIR) / "data"
DEFAULT_FUEL_PRICES_CSV: Path = DATA_DIR / "fuel-prices-for-be-assessment.csv"
DEFAULT_US_CITIES_CSV: Path = DATA_DIR / "us_cities.csv"
US_CITIES_DOWNLOAD_URL: str = (
    "https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv"
)
CITY_FUZZY_MATCH_CUTOFF: float = 0.85

# The price file has some Canadian stations, we skip them
CANADIAN_PROVINCE_CODES: frozenset[str] = frozenset(
    {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
)

# (min_lat, max_lat, min_lng, max_lng) - quick filter before the polygon check.
# These boxes include parts of Canada/Mexico, us_boundary.json does the real check.
USA_BOUNDING_BOXES: tuple[tuple[float, float, float, float], ...] = (
    (24.396308, 49.384358, -124.848974, -66.885444),  # contiguous US
    (51.214183, 71.538800, -179.148909, -129.979500),  # Alaska
)
USA_BOUNDARY_FILE: Path = DATA_DIR / "us_boundary.json"
# small margin for coastal points and islands the outline misses
USA_COAST_TOLERANCE_MILES: float = 0.5

SAME_LOCATION_MILES: float = 0.1

# e.g. "Toronto, Ontario" or "Monterrey, Mexico"
NON_US_REGION_NAMES: frozenset[str] = frozenset(
    {"canada", "mexico", "méxico", "ontario", "quebec", "british columbia", "alberta", "manitoba",
     "saskatchewan", "nova scotia", "new brunswick", "newfoundland", "prince edward island", "yukon"}
)

# HTTP and caching
HTTP_TIMEOUT_SECONDS: float = 15.0
ROUTE_CACHE_TIMEOUT_SECONDS: int = 60 * 60 * 24
GEOCODE_CACHE_TIMEOUT_SECONDS: int = 60 * 60 * 24 * 7
PLAN_CACHE_TIMEOUT_SECONDS: int = 60 * 60

CACHE_PREFIX_ROUTE = "osrm-route"
CACHE_PREFIX_GEOCODE = "geocode"
CACHE_PREFIX_PLAN = "fuel-plan"

OSRM_PROFILE = "driving"
NOMINATIM_COUNTRY_CODE = "us"
