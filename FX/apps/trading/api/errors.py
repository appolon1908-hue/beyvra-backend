from rest_framework.response import Response


MESSAGES = {
    "FEATURE_DISABLED": "This feature is not enabled.",
    "RESOURCE_NOT_FOUND": "The requested resource was not found.",
    "IDEMPOTENCY_CONFLICT": "The idempotency key was used with a different request.",
    "TRADING_HALTED": "Trading is halted for this scope.",
}


def error_response(request, code, status_code, details=None):
    return Response({"error": {"code": code, "message": MESSAGES.get(code, code.replace("_", " ").title()), "request_id": request.headers.get("X-Request-ID", ""), "details": details or {}}}, status=status_code)
