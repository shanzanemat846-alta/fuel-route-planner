from rest_framework import serializers

LOCATION_HELP = "'City, ST' (e.g. 'Chicago, IL'), 'lat,lng', or a US street address."


class RoutePlanRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=255, trim_whitespace=True, help_text=LOCATION_HELP)
    finish = serializers.CharField(max_length=255, trim_whitespace=True, help_text=LOCATION_HELP)
    include_geometry = serializers.BooleanField(
        default=True, help_text="Include the GeoJSON route/stops (set false for a lighter payload)."
    )

    def validate(self, attrs):
        if attrs["start"].lower() == attrs["finish"].lower():
            raise serializers.ValidationError("Start and finish must be different locations.")
        return attrs
