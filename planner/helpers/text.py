import re

# US state name -> USPS code, used to parse inputs like "Austin, Texas".
US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
US_STATE_CODES: frozenset[str] = frozenset(US_STATES.values())

_COORDINATE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_PREFIX_RULES = (
    (re.compile(r"^(st\.?|saint)\s+"), "saint "),
    (re.compile(r"^(ft\.?)\s+"), "fort "),
    (re.compile(r"^(mt\.?)\s+"), "mount "),
)


def normalize_city_name(name: str) -> str:
    """Lowercase, expand St./Ft./Mt. and drop punctuation, e.g. "St. Louis " -> "saint louis"."""
    value = (name or "").strip().lower()
    for pattern, replacement in _PREFIX_RULES:
        value = pattern.sub(replacement, value)
    value = re.sub(r"[^a-z ]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_coordinates(value: str) -> tuple[float, float] | None:
    """Parse "lat,lng". Returns None if it isn't a valid pair."""
    match = _COORDINATE_RE.match(value or "")
    if not match:
        return None
    lat, lng = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def looks_like_coordinates(value: str) -> bool:
    # also true for out of range input like "100,200"
    return bool(_COORDINATE_RE.match(value or ""))


def trailing_region(value: str) -> str | None:
    """Last part of "Place, REGION", e.g. "ON" for "Toronto, ON". None for addresses ending in a ZIP."""
    parts = [p.strip() for p in (value or "").split(",") if p.strip()]
    if parts and parts[-1].lower() in {"usa", "us", "united states", "united states of america"}:
        parts = parts[:-1]
    if len(parts) < 2 or any(ch.isdigit() for ch in parts[-1]):
        return None
    return parts[-1]


def parse_city_state(value: str) -> tuple[str, str] | None:
    """Parse "City, ST" or "City, State" (", USA" at the end is ok) into (normalized city, state code)."""
    parts = [p.strip() for p in (value or "").split(",") if p.strip()]
    if parts and parts[-1].lower() in {"usa", "us", "united states", "united states of america"}:
        parts = parts[:-1]
    if len(parts) != 2:
        return None
    city, state = parts
    state_code = state.upper() if state.upper() in US_STATE_CODES else US_STATES.get(state.lower())
    if not state_code:
        return None
    return normalize_city_name(city), state_code
