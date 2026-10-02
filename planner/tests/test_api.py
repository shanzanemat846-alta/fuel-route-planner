from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from planner.services.route_planner import RoutePlannerService
from planner.services.station_index import StationIndex
from planner.tests.factories import FakeRouter, make_city, make_station

# Chicago -> Denver along latitude ~41 (roughly 920 miles).
CHICAGO, DENVER = (41.88, -87.63), (41.0, -104.99)


class RoutePlanApiTests(TestCase):
    def setUp(self):
        cache.clear()
        StationIndex.invalidate()
        make_city("Chicago", "IL", *CHICAGO)
        make_city("Denver", "CO", *DENVER)
        # Stations every ~110 miles along the line with varying prices.
        for i, frac in enumerate([0.0, 0.12, 0.24, 0.36, 0.48, 0.6, 0.72, 0.84, 0.96]):
            lat = CHICAGO[0] + (DENVER[0] - CHICAGO[0]) * frac
            lng = CHICAGO[1] + (DENVER[1] - CHICAGO[1]) * frac
            make_station(100 + i, ["3.90", "3.40", "3.80", "3.10", "3.95", "3.60", "3.20", "3.99", "3.50"][i], lat, lng)
        make_station(999, "1.00", 30.0, -90.0)  # cheap but far off the route -> must be ignored

        self.router = FakeRouter()
        patcher = mock.patch(
            "planner.controllers.route_controller.RoutePlannerService",
            side_effect=lambda: RoutePlannerService(router=self.router),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(StationIndex.invalidate)

    def test_returns_plan_with_stops_cost_and_geojson(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "Chicago, IL", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["start"]["resolved_by"], "local_city_db")
        self.assertGreater(body["summary"]["number_of_stops"], 1)
        self.assertAlmostEqual(body["summary"]["total_gallons"], body["route"]["distance_miles"] / 10, delta=0.2)
        self.assertNotIn(999, [s["opis_id"] for s in body["fuel_stops"]])
        self.assertEqual(body["geojson"]["type"], "FeatureCollection")
        # Total equals the sum of the individual stops.
        self.assertAlmostEqual(sum(s["cost"] for s in body["fuel_stops"]), body["summary"]["total_fuel_cost"], delta=0.05)

    def test_detours_are_reported_separately_and_not_added_to_the_total(self):
        body = self.client.get(reverse("planner:route-plan"), {"start": "Chicago, IL", "finish": "Denver, CO"}).json()
        stops, summary, detour = body["fuel_stops"], body["summary"], body["detour_estimate"]
        for stop in stops:
            self.assertAlmostEqual(stop["detour"]["round_trip_miles"], 2 * stop["distance_from_route_miles"], delta=0.11)
            self.assertAlmostEqual(stop["detour"]["gallons"], stop["detour"]["round_trip_miles"] / 10, delta=0.011)
        # detours must not change the trip total
        self.assertAlmostEqual(sum(s["cost"] for s in stops), summary["total_fuel_cost"], delta=0.05)
        self.assertAlmostEqual(detour["cost"], sum(s["detour"]["cost"] for s in stops), delta=0.05)
        self.assertAlmostEqual(
            detour["total_fuel_cost_with_detours"], summary["total_fuel_cost"] + detour["cost"], delta=0.02
        )

    def test_single_routing_call_and_cache_hit(self):
        params = {"start": "Chicago, IL", "finish": "Denver, CO"}
        self.client.get(reverse("planner:route-plan"), params)
        second = self.client.get(reverse("planner:route-plan"), params).json()
        self.assertEqual(self.router.calls, 1)
        self.assertTrue(second["meta"]["cached"])

    def test_post_and_lat_lng_input(self):
        response = self.client.post(
            reverse("planner:route-plan"),
            {"start": "41.88,-87.63", "finish": "Denver, CO", "include_geometry": False},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("geojson", response.json())

    def test_validation_error(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "Chicago, IL"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_location_outside_usa(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "51.05,-114.07", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "location_outside_usa")

    def test_non_us_region_is_rejected_before_address_lookup(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "Toronto, ON", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "location_outside_usa")

    def test_unknown_state_code_is_not_found(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "Springfield, ZZ", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 404)

    def test_canadian_coordinates_are_rejected(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "43.6532,-79.3832", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "location_outside_usa")

    def test_out_of_range_coordinates_are_invalid(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "100,200", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_location")

    def test_same_place_spelled_differently(self):
        response = self.client.get(reverse("planner:route-plan"), {"start": "Chicago, IL", "finish": "chicago,IL"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "same_location")
        self.assertEqual(self.router.calls, 0)

    def test_map_page_shows_readable_validation_errors(self):
        response = self.client.get(reverse("planner:route-map"), {"start": "Chicago, IL"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "finish: This field is required.", status_code=400)
        self.assertNotContains(response, "ErrorDetail", status_code=400)

    def test_map_page_without_params_shows_the_form(self):
        response = self.client.get(reverse("planner:route-map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form class="planner"')
        self.assertNotContains(response, "role=\"alert\"")
        self.assertEqual(self.router.calls, 0)

    def test_map_page_error_keeps_the_typed_values(self):
        response = self.client.get(reverse("planner:route-map"), {"start": "Toronto, ON", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "is outside the USA", status_code=422)
        self.assertContains(response, 'value="Toronto, ON"', status_code=422)

    def test_root_redirects_to_the_planner_page(self):
        response = self.client.get("/", {"start": "Chicago, IL", "finish": "Denver, CO"})
        self.assertRedirects(
            response, reverse("planner:route-map") + "?start=Chicago%2C+IL&finish=Denver%2C+CO", fetch_redirect_response=False
        )

    def test_map_page_renders(self):
        response = self.client.get(reverse("planner:route-map"), {"start": "Chicago, IL", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "plan-geojson")

    def test_health(self):
        self.assertEqual(self.client.get(reverse("planner:health")).json()["stations_loaded"], 10)
