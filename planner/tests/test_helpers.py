import numpy as np
from django.test import SimpleTestCase

from planner.helpers.geo import (
    chord_to_miles,
    cumulative_distances_miles,
    haversine_miles,
    is_within_usa,
    miles_to_chord,
    resample_indices,
)
from planner.helpers.text import (
    looks_like_coordinates,
    normalize_city_name,
    parse_city_state,
    parse_coordinates,
    trailing_region,
)


class GeoHelperTests(SimpleTestCase):
    def test_haversine_nyc_to_la(self):
        self.assertAlmostEqual(haversine_miles(40.7128, -74.0060, 34.0522, -118.2437), 2445, delta=5)

    def test_cumulative_and_resample(self):
        coords = np.column_stack((np.linspace(40, 41, 500), np.full(500, -90.0)))
        cumulative = cumulative_distances_miles(coords)
        self.assertAlmostEqual(cumulative[-1], 69.1, delta=0.2)
        idx = resample_indices(cumulative, 10)
        self.assertEqual(idx[-1], 499)
        self.assertTrue(6 <= len(idx) <= 9)

    def test_chord_round_trip(self):
        self.assertAlmostEqual(float(chord_to_miles(miles_to_chord(25.0))), 25.0, places=6)

    def test_is_within_usa(self):
        self.assertTrue(is_within_usa(39.0, -98.0))
        self.assertFalse(is_within_usa(51.05, -114.07))  # Calgary

    def test_is_within_usa_rejects_canada_and_mexico_inside_the_bounding_box(self):
        for lat, lng in [(43.6532, -79.3832), (45.50, -73.57), (48.43, -123.37),  # Toronto, Montreal, Victoria
                         (25.6866, -100.3161), (32.51, -117.04), (31.69, -106.42),  # Monterrey, Tijuana, Juarez
                         (42.30, -83.03), (25.87, -97.50), (25.04, -77.35)]:       # Windsor, Matamoros, Nassau
            with self.subTest(lat=lat, lng=lng):
                self.assertFalse(is_within_usa(lat, lng))

    def test_is_within_usa_accepts_border_and_coastal_cities(self):
        for lat, lng in [(42.3314, -83.0458), (31.7619, -106.485), (25.9017, -97.4975),  # Detroit, El Paso, Brownsville
                         (24.5551, -81.78), (35.25, -75.53), (43.09, -79.06),            # Key West, Hatteras, Niagara Falls NY
                         (40.7128, -74.0060), (61.2181, -149.9003), (48.99, -122.75)]:   # NYC, Anchorage, Blaine WA
            with self.subTest(lat=lat, lng=lng):
                self.assertTrue(is_within_usa(lat, lng))


class TextHelperTests(SimpleTestCase):
    def test_normalize_city_name(self):
        self.assertEqual(normalize_city_name(" St. Louis "), "saint louis")
        self.assertEqual(normalize_city_name("Ft Worth"), "fort worth")

    def test_parse_coordinates(self):
        self.assertEqual(parse_coordinates("40.7, -74.0"), (40.7, -74.0))
        self.assertIsNone(parse_coordinates("Chicago, IL"))
        self.assertIsNone(parse_coordinates("200, 10"))

    def test_looks_like_coordinates(self):
        self.assertTrue(looks_like_coordinates("100,200"))
        self.assertTrue(looks_like_coordinates("40.7, -74.0"))
        self.assertFalse(looks_like_coordinates("Chicago, IL"))

    def test_trailing_region(self):
        self.assertEqual(trailing_region("Toronto, ON"), "ON")
        self.assertEqual(trailing_region("Monterrey, Mexico, USA"), "Mexico")
        self.assertIsNone(trailing_region("Chicago"))
        self.assertIsNone(trailing_region("40.7, -74.0"))
        self.assertIsNone(trailing_region("123 Main St, Springfield, IL 62701"))

    def test_parse_city_state(self):
        self.assertEqual(parse_city_state("Austin, Texas"), ("austin", "TX"))
        self.assertEqual(parse_city_state("St. Louis, MO, USA"), ("saint louis", "MO"))
        self.assertIsNone(parse_city_state("Somewhere, ZZ"))
