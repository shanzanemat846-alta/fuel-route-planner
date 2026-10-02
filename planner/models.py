from django.db import models


class City(models.Model):
    """City centre coordinates, used to place stations and to resolve "City, ST" inputs."""

    name = models.CharField(max_length=128)
    normalized_name = models.CharField(max_length=128)
    state_code = models.CharField(max_length=2)
    state_name = models.CharField(max_length=64)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        verbose_name_plural = "cities"
        indexes = [models.Index(fields=["state_code", "normalized_name"])]

    def __str__(self) -> str:
        return f"{self.name}, {self.state_code}"


class FuelStation(models.Model):
    """Truck stop with its retail price. Lat/lng is the centre of its city (the CSV has no coordinates)."""

    opis_id = models.PositiveIntegerField(unique=True, help_text="OPIS Truckstop ID")
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=5)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["retail_price"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) ${self.retail_price}"
