from rest_framework.response import Response
from rest_framework.views import APIView

from planner.models import FuelStation


class HealthController(APIView):
    """GET /api/v1/health/"""

    def get(self, request):
        return Response({"status": "ok", "stations_loaded": FuelStation.objects.count()})
