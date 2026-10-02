"""
Loads the fuel price CSV into the database.

The CSV has no coordinates, so each station gets the coordinates of its city
(from a US cities dataset). Done once here so requests never have to geocode
stations. Canadian rows are skipped and duplicate OPIS ids keep the lowest price.
"""
import csv
import difflib
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.db import transaction

from planner.constants import (
    CANADIAN_PROVINCE_CODES,
    CITY_FUZZY_MATCH_CUTOFF,
    HTTP_TIMEOUT_SECONDS,
    US_CITIES_DOWNLOAD_URL,
)
from planner.helpers.text import normalize_city_name
from planner.models import City, FuelStation
from planner.services.station_index import StationIndex

logger = logging.getLogger(__name__)
BULK_BATCH_SIZE = 1000


@dataclass
class ImportReport:
    cities_loaded: int = 0
    rows_read: int = 0
    skipped_non_us: int = 0
    skipped_invalid: int = 0
    duplicates_merged: int = 0
    fuzzy_matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    stations_saved: int = 0


class StationImportService:
    def run(self, fuel_csv: Path, cities_csv: Path) -> ImportReport:
        report = ImportReport()
        self._ensure_cities_file(cities_csv)
        with transaction.atomic():
            lookup = self._load_cities(cities_csv, report)
            stations = self._read_stations(fuel_csv, lookup, report)
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations, batch_size=BULK_BATCH_SIZE)
            report.stations_saved = len(stations)
        StationIndex.invalidate()
        return report

    @staticmethod
    def _ensure_cities_file(path: Path) -> None:
        if path.exists():
            return
        logger.info("Downloading US cities dataset to %s", path)
        response = requests.get(US_CITIES_DOWNLOAD_URL, timeout=HTTP_TIMEOUT_SECONDS * 4)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)

    @staticmethod
    def _load_cities(path: Path, report: ImportReport) -> dict[str, dict[str, City]]:
        # returns {state_code: {normalized_name: City}}
        cities: list[City] = []
        lookup: dict[str, dict[str, City]] = {}
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                city = City(
                    name=row["CITY"].strip(),
                    normalized_name=normalize_city_name(row["CITY"]),
                    state_code=row["STATE_CODE"].strip().upper(),
                    state_name=row["STATE_NAME"].strip(),
                    latitude=float(row["LATITUDE"]),
                    longitude=float(row["LONGITUDE"]),
                )
                # some states list the same city twice, keep the first one
                if city.normalized_name not in lookup.setdefault(city.state_code, {}):
                    lookup[city.state_code][city.normalized_name] = city
                    cities.append(city)
        City.objects.all().delete()
        City.objects.bulk_create(cities, batch_size=BULK_BATCH_SIZE)
        report.cities_loaded = len(cities)
        return lookup

    def _read_stations(self, path: Path, lookup: dict, report: ImportReport) -> list[FuelStation]:
        by_opis_id: dict[int, FuelStation] = {}
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                report.rows_read += 1
                row = {k.strip(): (v or "").strip() for k, v in raw.items()}
                state = row["State"].upper()
                if state in CANADIAN_PROVINCE_CODES:
                    report.skipped_non_us += 1
                    continue
                try:
                    opis_id = int(row["OPIS Truckstop ID"])
                    price = Decimal(row["Retail Price"])
                except (ValueError, InvalidOperation):
                    report.skipped_invalid += 1
                    continue

                city = self._match_city(row["City"], state, lookup, report)
                if city is None:
                    report.unmatched.append(f"{row['City']}, {state}")
                    continue

                existing = by_opis_id.get(opis_id)
                if existing is not None:
                    report.duplicates_merged += 1
                    if existing.retail_price <= price:
                        continue
                by_opis_id[opis_id] = FuelStation(
                    opis_id=opis_id,
                    name=row["Truckstop Name"],
                    address=row["Address"],
                    city=row["City"],
                    state=state,
                    rack_id=int(row["Rack ID"]) if row.get("Rack ID", "").isdigit() else None,
                    retail_price=price,
                    latitude=city.latitude,
                    longitude=city.longitude,
                )
        return list(by_opis_id.values())

    @staticmethod
    def _match_city(name: str, state: str, lookup: dict, report: ImportReport) -> City | None:
        state_cities = lookup.get(state, {})
        normalized = normalize_city_name(name)
        if normalized in state_cities:
            return state_cities[normalized]
        match = difflib.get_close_matches(normalized, state_cities.keys(), n=1, cutoff=CITY_FUZZY_MATCH_CUTOFF)
        if match:
            report.fuzzy_matched += 1
            return state_cities[match[0]]
        return None
