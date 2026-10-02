# Fuel Route Planner API

A Django 6.1 + Django REST Framework API that takes a **start** and **finish** location in the USA and returns:

- the driving route (distance, duration, GeoJSON geometry and an HTML map),
- the **cost-optimal fuel stops** along the route for a vehicle with a **500 mile range**,
- the **total money spent on fuel** at **10 MPG**, using the provided fuel price file.

Only **one external API call** (OSRM routing) is made per request, and the planning itself runs in roughly **20 ms**.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

python manage.py migrate
python manage.py load_fuel_stations     # one-off: cleans + geocodes the price CSV (~5 s)
python manage.py runserver
```

Try it:

```bash
curl "http://127.0.0.1:8000/api/v1/route/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```

To see the map, open this in a browser: <http://127.0.0.1:8000/api/v1/route/map/?start=New York, NY&finish=Los Angeles, CA>

To use Postman, import `postman_collection.json`.

Run the tests with `python manage.py test planner`.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/route/?start=…&finish=…` | Plan a trip (query params) |
| `POST` | `/api/v1/route/` | Plan a trip (JSON body) |
| `GET` | `/api/v1/route/map/?start=…&finish=…` | Interactive Leaflet map of the plan |
| `GET` | `/api/v1/health/` | Liveness + number of stations loaded |

### Request

```json
{ "start": "New York, NY", "finish": "Los Angeles, CA", "include_geometry": true }
```

`start` and `finish` can each be given in any of these forms:

- `"City, ST"` or `"City, State"`, e.g. `"Chicago, IL"` or `"Austin, Texas"`. These are resolved locally, with **no external call**.
- `"lat,lng"`, e.g. `"41.8781,-87.6298"`. These are also resolved with **no external call**.
- Any US address, e.g. `"1600 Pennsylvania Ave, Washington DC"`. These fall back to Nominatim (OpenStreetMap) and are cached.

Set `include_geometry` to `false` to omit the GeoJSON and get a lighter payload.

### Response (abridged, illustrative values)

```json
{
  "start":  { "query": "New York, NY", "label": "New York, NY", "latitude": 40.748, "longitude": -73.997, "resolved_by": "local_city_db" },
  "finish": { "...": "..." },
  "route":  { "distance_miles": 2789.4, "duration_hours": 41.2 },
  "fuel_stops": [
    {
      "sequence": 1, "opis_id": 40084, "name": "7-ELEVEN #40084",
      "address": "I-95, EXIT 70", "city": "Palisades Park", "state": "NJ",
      "latitude": 40.848, "longitude": -73.997,
      "price_per_gallon": 3.099, "mile_marker": 0.0, "distance_from_route_miles": 3.1,
      "gallons": 43.2, "cost": 133.88
    }
  ],
  "summary": {
    "total_fuel_cost": 793.73, "total_gallons": 278.94, "number_of_stops": 10,
    "average_price_per_gallon": 2.988, "vehicle_range_miles": 500, "vehicle_mpg": 10,
    "starts_with_full_tank": false
  },
  "map_url": "/api/v1/route/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA",
  "geojson": { "type": "FeatureCollection", "features": ["route LineString", "start/finish/fuel-stop Points"] },
  "meta": { "station_corridor_miles": 10, "cached": false, "compute_time_ms": 642.1 }
}
```

The `geojson` field can be pasted straight into <https://geojson.io> to view the route.

**Detours (informational, not in the total).** Stations are geocoded to their city centre, so reaching one
means leaving the route and coming back. Each stop has a `detour` object (`one_way_miles`, `round_trip_miles`,
`gallons`, `cost`), and the top-level `detour_estimate` sums them and gives `total_fuel_cost_with_detours`.
These are straight-line estimates and are **not** added to `summary.total_fuel_cost`.

### Errors

Every error uses the same shape:

```json
{ "error": { "code": "location_outside_usa", "message": "..." } }
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Missing or invalid parameters |
| 400 | `invalid_location` | A `lat,lng` pair is out of range (e.g. `100,200`) |
| 400 | `same_location` | Start and finish resolve to the same place (e.g. `Chicago, IL` and `chicago,IL`) |
| 404 | `location_not_found` | The location could not be geocoded, or `City, XX` uses an unknown state code |
| 422 | `location_outside_usa` | A point lies outside the USA (checked against US state outlines, so Canada/Mexico are rejected) |
| 422 | `route_not_found` | OSRM found no drivable route |
| 422 | `no_feasible_fuel_plan` | Some stretch of the route has no station within 500 miles |
| 502 | `external_service_error` | The routing or geocoding provider failed |
| 503 | `station_data_not_loaded` | `load_fuel_stations` has not been run |

---

## Architecture

```
request ─► Controller ─► Serializer (validate)
                │
                ▼
        RoutePlannerService (orchestrator, caches the final payload)
          ├─ GeocodingService   coords ─► local City table ─► Nominatim fallback
          ├─ RoutingService     1 × OSRM call (cached per coordinate pair)
          ├─ StationIndex       in-memory numpy arrays + KD-tree corridor search
          └─ fuel_optimizer     pure, optimal greedy algorithm
```

```
config/                     Django project (settings, root urls, wsgi/asgi)
planner/
  constants.py              business rules (range, MPG, corridor, cache TTLs, URLs)
  exceptions.py             domain errors + DRF handler that produces uniform JSON errors
  dtos.py                   immutable dataclasses passed between services
  models.py                 City, FuelStation
  serializers.py            request validation
  urls.py                   API routes
  controllers/              thin HTTP layer (APIView / View classes)
  services/                 business logic (see diagram above) + CSV import service
  helpers/                  pure functions: geo maths, text parsing, cache keys
  management/commands/      load_fuel_stations
  templates/planner/        Leaflet map page
  tests/                    unit tests (optimizer, helpers) + API tests with a fake router
data/                       provided fuel price CSV + US cities dataset + US outline (us_boundary.json, Census 1:5M)
```

The design follows a few principles:

- **Controllers are thin.** They validate input, call one service and return the result. All logic lives in the services.
- **The optimizer is pure Python** with no Django or database dependency, so it is easy to test and reason about.
- **Dependencies are injected.** `RoutePlannerService(router=…)` lets the tests run without any network access.

---

## How it works

### 1. Geocoding the stations (offline, once)

The price file has no coordinates. Geocoding about 8,000 rows through a free API on every request would be slow and would break the "few external calls" requirement.

Instead, `load_fuel_stations` geocodes each station **once** to its city centroid, using the public [US Cities Database](https://github.com/kelvins/US-Cities-Database). During the import it also cleans the data:

- It strips stray whitespace from every field.
- It drops the 620 Canadian rows, because the API is USA only.
- It de-duplicates by OPIS ID and keeps the lowest price (902 duplicates are merged).
- It matches cities exactly first, then fuzzily within the same state (which handles cases like `St.` versus `Saint`).

The result is 6,615 US stations, with **99.8 %** matched to a city.

### 2. Routing (the single external call)

The [OSRM](https://project-osrm.org/) public server is free and needs no API key. One request returns the full route geometry, its distance and its duration. Responses are cached.

### 3. Finding stations along the route

1. The route polyline is resampled to one point every 0.5 miles.
2. A KD-tree is built over those points, using 3-D unit-sphere coordinates so that distances are accurate.
3. **All** stations are queried against the tree in one vectorised call. This gives each station's distance from the route and its mile marker along the route.

The search uses a 10-mile corridor because stations are placed at their city centre. If the trip turns out to be infeasible (for example on sparse rural stretches), the corridor widens automatically to 25 and then 50 miles.

### 4. Choosing the fuel stops

This is the classic gas-station-problem greedy, which is provably optimal for a fixed route. At each station:

1. If a **cheaper** station is reachable within 500 miles, buy only enough fuel to reach it.
2. Otherwise, if the destination is within range, buy just enough fuel to finish.
3. Otherwise, **fill up** here, then drive to the cheapest station within range.

This runs in roughly O(n·k) time, where k is the number of stations within range.

---

## Assumptions

- **The vehicle starts with an empty tank,** so `total_fuel_cost` is the cost of all fuel needed for the trip. The first stop is the first station near the origin. The few miles driven to reach it are billed at that station's price.
  - To instead start with a full tank and report only en-route purchases, set `START_WITH_FULL_TANK = True` in `constants.py`.
- **Stations are located at their city centroid.** The detour from the route to a station is reported as `distance_from_route_miles`, but it is not added to the fuel cost.
- **Minimising cost can produce a few small top-ups.** The cheapest plan sometimes buys only a few gallons to reach a much cheaper station. This is optimal for cost, but a minimum-purchase rule could be added if fewer stops were preferred.
- **The vehicle does not end the trip with spare fuel.** It buys exactly the fuel needed to reach the destination.

---

## Performance

These figures are for New York → Los Angeles, with a route of about 30,000 points and 6,615 stations:

| Step | Time |
|---|---|
| OSRM route call (network) | ~0.5–1.5 s |
| Station matching + optimisation + payload | ~20 ms |
| Repeated request (cached) | < 1 ms |

The station index is built lazily on the first request, which takes about 150 ms once per process.

For production, I would:

- point `OSRM_BASE_URL` at a self-hosted OSRM instance,
- switch to Redis for the cache so that all workers share it, and
- run behind gunicorn or uvicorn.
