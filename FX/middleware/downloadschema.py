import secrets

from django.conf import settings
from django.http import JsonResponse

class APIKeyMiddlewareDownloadSchema:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/api/schema/":
            supplied = request.headers.get("X-API-KEY", "")
            configured = settings.SCHEMA_API_KEY
            if not configured or not secrets.compare_digest(supplied, configured):
                return JsonResponse({"detail": "Unauthorized"}, status=401)

        return self.get_response(request)
