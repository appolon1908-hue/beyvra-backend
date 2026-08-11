from rest_framework.response import Response


MESSAGES = {
    "FEATURE_DISABLED": "This feature is not enabled.",
    "RESOURCE_NOT_FOUND": "The requested resource was not found.",
    "IDEMPOTENCY_CONFLICT": "The idempotency key was used with a different request.",
    "TRADING_HALTED": "Trading is halted for this scope.",
    "KYC_REQUIRED": "Identity verification is required.",
    "KYC_PENDING": "Identity verification is pending.",
    "KYC_REJECTED": "Identity verification was not approved.",
    "AML_REVIEW": "Your account is being reviewed.",
    "AML_BLOCKED": "Trading is unavailable for this account.",
    "SANCTIONS_REVIEW": "Your account is being reviewed.",
    "SANCTIONS_BLOCKED": "Trading is unavailable for this account.",
    "JURISDICTION_RESTRICTED": "Trading is unavailable in your jurisdiction.",
    "ACCOUNT_RESTRICTED": "Your account is restricted.",
    "ACCOUNT_SUSPENDED": "Your account is suspended.",
    "TRADING_DISABLED": "Trading is disabled for this account.",
    "MANUAL_REVIEW_REQUIRED": "Your account is being reviewed.",
    "INVALID_ORDER": "The order details are invalid.",
}


def error_response(request, code, status_code, details=None):
    payload = {"code": code, "message": MESSAGES.get(code, code.replace("_", " ").title())}
    if details:
        payload["details"] = details
    return Response({"error": payload}, status=status_code)
