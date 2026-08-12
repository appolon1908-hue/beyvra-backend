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
}


def error_response(request, code, status_code, details=None):
    return Response({"error": {"code": code, "message": MESSAGES.get(code, code.replace("_", " ").title()), "request_id": request.headers.get("X-Request-ID", ""), "details": details or {}}}, status=status_code)
