from django.test import SimpleTestCase

from planner.exceptions import NoFeasibleFuelPlanError
from planner.services.fuel_optimizer import optimize_fuel_stops
from planner.tests.factories import station

RANGE, MPG = 500.0, 10.0


def plan(stations, miles, full=False):
    return optimize_fuel_stops(stations, miles, RANGE, MPG, start_with_full_tank=full)


class FuelOptimizerTests(SimpleTestCase):
    def test_short_trip_single_stop_buys_exact_fuel(self):
        result = plan([station(0, 4.0)], 300)
        self.assertEqual(len(result.stops), 1)
        self.assertAlmostEqual(result.total_gallons, 30.0)
        self.assertAlmostEqual(result.total_cost, 120.0)

    def test_empty_start_always_buys_fuel_for_whole_trip(self):
        stations = [station(m, p, i) for i, (m, p) in enumerate([(2, 4.0), (300, 3.5), (650, 3.9), (900, 3.2)])]
        result = plan(stations, 1200)
        self.assertAlmostEqual(result.total_gallons, 120.0)

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        stations = [station(0, 4.0, 0), station(200, 3.0, 1)]
        result = plan(stations, 600)
        first, second = result.stops
        self.assertAlmostEqual(first.gallons, 20.0)   # 200 mi at $4
        self.assertAlmostEqual(second.gallons, 40.0)  # 400 mi at $3
        self.assertAlmostEqual(result.total_cost, 80 + 120)

    def test_fills_up_when_current_station_is_cheapest_in_range(self):
        stations = [station(0, 3.0, 0), station(400, 4.0, 1), station(450, 5.0, 2)]
        result = plan(stations, 800)
        self.assertAlmostEqual(result.stops[0].gallons, 50.0)  # full tank at the cheap station
        self.assertAlmostEqual(result.total_gallons, 80.0)
        # 400 mi remain from mile 400 with 100 mi in the tank -> buy 300 mi at $4.
        self.assertAlmostEqual(result.total_cost, 150 + 120)

    def test_is_cheaper_than_naive_nearest_station_strategy(self):
        stations = [station(0, 5.0, 0), station(100, 2.0, 1), station(450, 5.0, 2), station(550, 2.5, 3)]
        result = plan(stations, 1000)
        self.assertLess(result.total_cost, 1000 / MPG * 5.0)
        self.assertNotIn(2, [s.station.station_index for s in result.stops])

    def test_never_exceeds_tank_capacity(self):
        stations = [station(m, 3.0 + (m % 7) / 10, i) for i, m in enumerate(range(0, 2500, 90))]
        result = plan(stations, 2500)
        for stop in result.stops:
            self.assertLessEqual(stop.gallons, RANGE / MPG + 1e-6)
        self.assertAlmostEqual(result.total_gallons, 250.0)

    def test_full_tank_start_no_purchase_for_short_trip(self):
        result = plan([station(10, 3.0)], 400, full=True)
        self.assertEqual(result.stops, [])
        self.assertEqual(result.total_cost, 0)

    def test_gap_larger_than_range_raises(self):
        with self.assertRaises(NoFeasibleFuelPlanError):
            plan([station(0, 3.0), station(600, 3.0)], 900)

    def test_no_station_raises(self):
        with self.assertRaisesMessage(NoFeasibleFuelPlanError, "No fuel stations found along the route."):
            plan([], 100)

    def test_first_station_out_of_range_raises_with_its_own_message(self):
        with self.assertRaisesMessage(NoFeasibleFuelPlanError, "No fuel station within 500 miles of the start"):
            plan([station(600, 3.0)], 900)
