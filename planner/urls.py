from django.urls import path

from planner.controllers.health_controller import HealthController
from planner.controllers.route_controller import RouteMapController, RoutePlanController

app_name = "planner"

urlpatterns = [
    path("health/", HealthController.as_view(), name="health"),
    path("route/", RoutePlanController.as_view(), name="route-plan"),
    path("route/map/", RouteMapController.as_view(), name="route-map"),
]
