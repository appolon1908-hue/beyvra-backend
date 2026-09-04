class SensitiveResponseNoStoreMiddleware:
    """Prevent browsers and intermediaries from retaining API/auth evidence."""

    SENSITIVE_PREFIXES = (
        "/api/",
        "/auth/",
        "/ws/",
        "/login",
        "/logout",
        "/register",
        "/forgot-password",
        "/password-reset",
        "/session-expired",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.SENSITIVE_PREFIXES):
            response["Cache-Control"] = "private, no-store"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
