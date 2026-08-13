HIGH_RISK={"GLOBAL_PLATFORM_HALT","TRADING_HALT","EXECUTION_HALT","WITHDRAWAL_HALT","SETTLEMENT_HALT","TREASURY_HALT"}
ALL_CODES=HIGH_RISK|{"MARKET_DATA_PROVIDER_HALT","NEWS_PROVIDER_HALT","DEVELOPER_API_HALT","REALTIME_HALT"}
def effective_active(states,code):
    global_state=states.get("GLOBAL_PLATFORM_HALT")
    if global_state is None or global_state=="ACTIVE":return True
    state=states.get(code)
    return True if code in HIGH_RISK and state is None else state=="ACTIVE"
