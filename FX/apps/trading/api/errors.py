from rest_framework.response import Response


MESSAGES = {
    "FEATURE_DISABLED": "This feature is not enabled.",
    "RESOURCE_NOT_FOUND": "The requested resource was not found.",
    "IDEMPOTENCY_CONFLICT": "The idempotency key was used with a different request.",
    "TRADING_HALTED": "Trading is halted for this scope.",
    "MARKET_DATA_STALE": "Current market data is temporarily unavailable.",
    "INSUFFICIENT_AVAILABLE_BALANCE": "The simulated available balance is insufficient.",
    "INSUFFICIENT_AVAILABLE_POSITION": "The simulated available position is insufficient.",
    "ORDER_INVALID_STATE": "This simulated order can no longer be changed.",
    "VALIDATION_ERROR": "Some order information needs to be corrected.",
    "SIMULATION_AUTHORITY_REQUIRED": "Simulation authority is required.",
    "TRADING_NOT_AVAILABLE": "Trading is not available for this account or instrument.",
    "ORDER_REJECTED": "The order could not be accepted.",
    "ACCOUNT_REVIEW_REQUIRED": "Your account is being reviewed.",
    "SURVEILLANCE_TEMPORARILY_UNAVAILABLE": "Trading controls are temporarily unavailable.",
    "PERMISSION_DENIED": "You do not have permission to perform this action.",
    "SELF_APPROVAL_FORBIDDEN": "Independent approval is required.",
    "TRADE_NOT_FOUND": "The trade could not be found.",
    "SETTLEMENT_NOT_FOUND": "The settlement record could not be found.",
    "POST_TRADE_EXCEPTION": "This trade requires review.",
    "SETTLEMENT_PENDING": "Settlement is pending.",
    "SETTLEMENT_UNAVAILABLE": "Settlement information is temporarily unavailable.",
}


def error_response(request, code, status_code, details=None):
    return Response({"error": {"code": code, "message": MESSAGES.get(code, "The request could not be completed."), "details": details or {}}}, status=status_code)
