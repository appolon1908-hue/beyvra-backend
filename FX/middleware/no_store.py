from django.utils.cache import patch_cache_control


class SensitiveResponseNoStoreMiddleware:
    """Preserve explicit no-store policies; protect other API/auth responses."""

    SENSITIVE_PREFIXES = (
        "/api/", "/auth/", "/ws/", "/login", "/logout", "/register",
        "/forgot-password", "/password-reset", "/session-expired",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.SENSITIVE_PREFIXES):
            directives = {
                value.strip().lower()
                for value in response.get("Cache-Control", "").split(",")
            }
            if "no-store" not in directives or "public" in directives:
                patch_cache_control(response, private=True, no_store=True)
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
