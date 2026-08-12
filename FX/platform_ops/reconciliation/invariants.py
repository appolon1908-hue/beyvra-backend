CHECKS=("ORDER_EXECUTION_MISMATCH","EXECUTION_TRADE_MISMATCH","TRADE_POSITION_MISMATCH","POSITION_PNL_MISMATCH","FEE_MISMATCH","TREASURY_FUNDING_MISMATCH","POST_TRADE_SETTLEMENT_MISMATCH","REGULATORY_RECORD_GAP","AUDIT_GAP","OUTBOX_GAP")
def summarize(results):
    violations=[{"check":k,"count":int(results.get(k,0))} for k in CHECKS if int(results.get(k,0))]
    return {"state":"PASS" if not violations else "FAIL","checks":{k:int(results.get(k,0)) for k in CHECKS},"violations":violations}
