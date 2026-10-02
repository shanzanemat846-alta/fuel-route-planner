"""
Cheapest fuel purchases along a fixed route (the "gas station problem").

Greedy, at each station:
  1. a cheaper station is within range -> buy just enough to reach it
  2. the finish is within range -> buy just enough to finish
  3. otherwise fill up here and go to the cheapest station in range

Fuel is tracked in miles of range and converted to gallons at the end.
"""
import math

from planner.dtos import FuelPlan, FuelStop, StationOnRoute
from planner.exceptions import NoFeasibleFuelPlanError

_EPSILON = 1e-6


def optimize_fuel_stops(
    stations: list[StationOnRoute],
    total_miles: float,
    max_range_miles: float,
    miles_per_gallon: float,
    start_with_full_tank: bool = False,
) -> FuelPlan:
    """
    With an empty tank, the miles driven to the first station are charged at
    that station's price so the total covers the whole trip.
    Raises NoFeasibleFuelPlanError if some gap is longer than the range.
    """
    stations = sorted(stations, key=lambda s: (s.route_mile, s.price))
    stations = [s for s in stations if s.route_mile < total_miles]
    purchases: dict[int, float] = {}  # station position -> miles of fuel bought

    if start_with_full_tank:
        current, position, fuel, current_price = -1, 0.0, max_range_miles, math.inf
        pre_trip_miles = 0.0
    else:
        if not stations:
            raise NoFeasibleFuelPlanError("No fuel stations found along the route.")
        if stations[0].route_mile > max_range_miles:
            raise NoFeasibleFuelPlanError(
                f"No fuel station within {max_range_miles:.0f} miles of the start of the route."
            )
        current, position, fuel = 0, stations[0].route_mile, 0.0
        current_price = stations[0].price
        pre_trip_miles = stations[0].route_mile

    while total_miles - position > fuel + _EPSILON:
        reach = position + max_range_miles

        # stations reachable on a full tank
        ahead: list[int] = []
        for j in range(current + 1, len(stations)):
            if stations[j].route_mile > reach + _EPSILON:
                break
            ahead.append(j)

        cheaper = next((j for j in ahead if stations[j].price < current_price), None)

        if cheaper is not None:
            target = cheaper
            needed = stations[target].route_mile - position
            _buy(purchases, current, max(0.0, needed - fuel))
            fuel = max(fuel, needed)
        elif total_miles <= reach + _EPSILON:
            _buy(purchases, current, total_miles - position - fuel)
            break
        elif ahead:
            _buy(purchases, current, max_range_miles - fuel)
            fuel = max_range_miles
            # on a price tie take the farthest one (fewer stops)
            target = min(ahead, key=lambda j: (stations[j].price, -stations[j].route_mile))
        else:
            gap_start = round(position)
            raise NoFeasibleFuelPlanError(
                f"No fuel station within {max_range_miles:.0f} miles after mile {gap_start} of the route."
            )

        fuel -= stations[target].route_mile - position
        position = stations[target].route_mile
        current, current_price = target, stations[target].price

    if pre_trip_miles > 0:
        _buy(purchases, 0, pre_trip_miles)

    return _build_plan(stations, purchases, miles_per_gallon)


def _buy(purchases: dict[int, float], station_pos: int, miles: float) -> None:
    # position -1 is the start of the route, nothing to buy there
    if station_pos >= 0 and miles > _EPSILON:
        purchases[station_pos] = purchases.get(station_pos, 0.0) + miles


def _build_plan(stations: list[StationOnRoute], purchases: dict[int, float], mpg: float) -> FuelPlan:
    stops: list[FuelStop] = []
    for pos in sorted(purchases):
        station = stations[pos]
        gallons = purchases[pos] / mpg
        stops.append(FuelStop(station=station, gallons=gallons, cost=gallons * station.price))
    return FuelPlan(
        stops=stops,
        total_gallons=sum(s.gallons for s in stops),
        total_cost=sum(s.cost for s in stops),
    )
