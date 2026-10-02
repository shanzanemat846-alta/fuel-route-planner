"""Planner errors. They all come back from the API as {"error": {"code": ..., "message": ...}}."""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class PlannerError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "planner_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidLocationError(PlannerError):
    code = "invalid_location"


class SameLocationError(PlannerError):
    code = "same_location"


class LocationNotFoundError(PlannerError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "location_not_found"


class LocationOutsideUSAError(PlannerError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "location_outside_usa"


class RouteNotFoundError(PlannerError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "route_not_found"


class ExternalServiceError(PlannerError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "external_service_error"


class NoFeasibleFuelPlanError(PlannerError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "no_feasible_fuel_plan"


class StationDataNotLoadedError(PlannerError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "station_data_not_loaded"


def api_exception_handler(exc, context):
    if isinstance(exc, PlannerError):
        logger.info("Planner error (%s): %s", exc.code, exc.message)
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=exc.status_code,
        )

    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            "error": {"code": "invalid_request", "message": "Invalid request.", "details": response.data}
        }
    return response
