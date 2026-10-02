"""
python manage.py load_fuel_stations [--csv prices.csv] [--cities us_cities.csv]
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from planner.constants import DEFAULT_FUEL_PRICES_CSV, DEFAULT_US_CITIES_CSV
from planner.services.station_import_service import StationImportService


class Command(BaseCommand):
    help = "Load fuel stations from the price CSV and geocode them to US city centroids."

    def add_arguments(self, parser):
        parser.add_argument("--csv", type=Path, default=DEFAULT_FUEL_PRICES_CSV, help="Fuel price CSV path.")
        parser.add_argument("--cities", type=Path, default=DEFAULT_US_CITIES_CSV, help="US cities CSV path.")

    def handle(self, *args, **options):
        report = StationImportService().run(options["csv"], options["cities"])
        self.stdout.write(f"Cities loaded:          {report.cities_loaded}")
        self.stdout.write(f"Price rows read:        {report.rows_read}")
        self.stdout.write(f"Skipped (non-US):       {report.skipped_non_us}")
        self.stdout.write(f"Skipped (invalid):      {report.skipped_invalid}")
        self.stdout.write(f"Duplicates merged:      {report.duplicates_merged}")
        self.stdout.write(f"Fuzzy city matches:     {report.fuzzy_matched}")
        self.stdout.write(f"Unmatched cities:       {len(report.unmatched)}")
        for item in sorted(set(report.unmatched)):
            self.stdout.write(f"    - {item}")
        self.stdout.write(self.style.SUCCESS(f"Stations saved:         {report.stations_saved}"))
