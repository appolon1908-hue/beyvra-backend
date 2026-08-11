from rest_framework.views import exception_handler

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
