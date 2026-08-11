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


def BeyvraErrorMapper(exc, context):  # noqa: N802 - public error-contract name
    response = exception_handler(exc, context)
    if response is None:
        if exc.__class__.__module__.startswith("redis"):
            from rest_framework.response import Response

            return Response(
                {
                    "code": "SERVICE_TEMPORARILY_UNAVAILABLE",
                    "message": "The service is temporarily unavailable.",
                },
                status=503,
            )
        return response
    if isinstance(exc, AuthenticationFailed):
        response.data = {
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid credentials.",
        }
        return response
    detail = getattr(exc, "detail", {})
    if isinstance(detail, dict) and str(detail.get("code", "")) == "FINANCIAL_WALLET_ID_NOT_ACCEPTED":
        response.data = {
            "code": "FINANCIAL_WALLET_ID_NOT_ACCEPTED",
            "message": "This wallet is not available for simulated trading.",
        }
        return response
    if "Real-money trading is disabled" in str(getattr(exc, "detail", "")):
        response.data = {
            "code": "FEATURE_DISABLED",
            "message": "This feature is currently unavailable.",
        }
        return response
    if "ACCOUNT_FROZEN" in str(getattr(exc, "detail", "")):
        response.data = {
            "code": "ACCOUNT_FROZEN",
            "message": "This account is temporarily restricted.",
        }
        return response
    code, message = SAFE_MESSAGES.get(
        response.status_code, ("REQUEST_FAILED", "The request could not be completed.")
    )
    response.data = {"code": code, "message": message}
    return response
