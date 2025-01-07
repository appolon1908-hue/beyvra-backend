from django.http import JsonResponse

class APIKeyMiddlewareDownloadSchema:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        API_KEY = "secret_key"

        if request.path == "/api/schema/" and request.headers.get("X-API-KEY") != API_KEY:
            return JsonResponse({"detail": "Unauthorized"}, status=401)

        return self.get_response(request)