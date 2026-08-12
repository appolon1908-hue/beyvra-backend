from rest_framework import exceptions, status
from rest_framework.views import exception_handler

SAFE_DOMAIN_ERRORS = {
    "FINANCIAL_WALLET_ID_NOT_ACCEPTED": "Real wallet identifiers are not valid for demo operations.",
}


def beyvra_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    if response is None or request is None or not request.path.startswith("/api/v1/"):
        return response
    if isinstance(exc, exceptions.NotAuthenticated):
        code, message = "AUTHENTICATION_REQUIRED", "Authentication is required."
    elif isinstance(exc, exceptions.PermissionDenied):
        code, message = "PERMISSION_DENIED", "You do not have permission to perform this action."
    elif isinstance(exc, exceptions.NotFound):
        code, message = "NOT_FOUND", "The requested resource was not found."
    elif isinstance(exc, exceptions.Throttled):
        code, message = "RATE_LIMITED", "Too many requests. Try again later."
    elif isinstance(exc, exceptions.ValidationError):
        code, message = "VALIDATION_ERROR", "The submitted information is invalid."
        if isinstance(response.data, dict):
            supplied_code = str(response.data.get("code", ""))
            if supplied_code in SAFE_DOMAIN_ERRORS:
                code, message = supplied_code, SAFE_DOMAIN_ERRORS[supplied_code]
    elif response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        code, message = "INTERNAL_ERROR", "The request could not be completed."
    else:
        code, message = "VALIDATION_ERROR", "The request could not be completed."
    response.data = {"error": {"code": code, "message": message}}
    return response
