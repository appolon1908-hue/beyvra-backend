HIGH_RISK={"REAL_TRADING_ENABLED","EXTERNAL_EXECUTION_ENABLED","REAL_SETTLEMENT_ENABLED","REAL_MONEY_ENABLED","REAL_WITHDRAWALS_ENABLED","REAL_TREASURY_TRANSFERS_ENABLED","LIVE_BROKER_ROUTING_ENABLED","FIX_LIVE_SESSION_ENABLED"}
def evaluate(code,value):
    if code in HIGH_RISK:
        if value is True:return False  # this readiness candidate never authorizes activation
        return False
    if isinstance(value,bool):return value
    return False

def inspect(code,value):
    configured_valid=isinstance(value,bool)
    configured_enabled=value is True
    high_risk=code in HIGH_RISK
    return {
        "effective_enabled":evaluate(code,value),
        "configured_valid":configured_valid,
        "unsafe_configuration":high_risk and configured_enabled,
        "fail_closed":high_risk,
    }
