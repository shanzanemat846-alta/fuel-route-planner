from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="planner:route-map", query_string=True)),
    path("admin/", admin.site.urls),
    path("api/v1/", include("planner.urls")),
]
