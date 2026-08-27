from rest_framework.views import exception_handler
from rest_framework.exceptions import AuthenticationFailed

SAFE_MESSAGES = {
    400: ("INVALID_REQUEST", "The request could not be processed."),
    401: ("AUTHENTICATION_REQUIRED", "Authentication is required."),
    403: ("ACTION_NOT_ALLOWED", "The requested action is not available."),
    404: ("RESOURCE_NOT_FOUND", "Resource not found."),
    405: ("METHOD_NOT_ALLOWED", "The requested action is not available."),
    429: ("RATE_LIMITED", "Please wait before trying again."),
}


def _safe_error(context, code, message, details=None):
    request = context.get("request")
    error = {"code": code, "message": message, "details": details or {}}
    return {
        "error": error,
        "code": code,
        "message": message,
        "details": error["details"],
        "instance": request.path if request is not None else "",
        "request_id": str(getattr(request, "request_id", "")) if request is not None else "",
    }


def BeyvraErrorMapper(exc, context):  # noqa: N802 - public error-contract name
    response = exception_handler(exc, context)
    if response is None:
        if exc.__class__.__module__.startswith("redis"):
            from rest_framework.response import Response

            return Response(_safe_error(context, "SERVICE_TEMPORARILY_UNAVAILABLE", "The service is temporarily unavailable."), status=503)
        return response
    if isinstance(exc, AuthenticationFailed):
        response.data = _safe_error(context, "INVALID_CREDENTIALS", "Invalid credentials.")
        return response
    detail = getattr(exc, "detail", {})
    if isinstance(detail, dict) and str(detail.get("code", "")) == "TENANT_SELECTION_REQUIRED":
        response.data = _safe_error(
            context,
            "TENANT_SELECTION_REQUIRED",
            "Select an active tenant with X-Organization-ID.",
        )
        return response
    if isinstance(detail, dict) and str(detail.get("code", "")) == "FINANCIAL_WALLET_ID_NOT_ACCEPTED":
        response.data = _safe_error(context, "FINANCIAL_WALLET_ID_NOT_ACCEPTED", "This wallet is not available for simulated trading.")
        return response
    if "Real-money trading is disabled" in str(getattr(exc, "detail", "")):
        response.data = _safe_error(context, "FEATURE_DISABLED", "This feature is currently unavailable.")
        return response
    if "ACCOUNT_FROZEN" in str(getattr(exc, "detail", "")):
        response.data = _safe_error(context, "ACCOUNT_FROZEN", "This account is temporarily restricted.")
        return response
    code, message = SAFE_MESSAGES.get(
        response.status_code, ("REQUEST_FAILED", "The request could not be completed.")
    )
    response.data = _safe_error(context, code, message)
    return response
