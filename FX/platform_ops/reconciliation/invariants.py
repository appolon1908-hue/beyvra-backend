CHECKS=("ORDER_EXECUTION_MISMATCH","EXECUTION_TRADE_MISMATCH","TRADE_POSITION_MISMATCH","POSITION_PNL_MISMATCH","FEE_MISMATCH","TREASURY_FUNDING_MISMATCH","POST_TRADE_SETTLEMENT_MISMATCH","REGULATORY_RECORD_GAP","AUDIT_GAP","OUTBOX_GAP")
def summarize(results):
    if results is None:
        return {"state":"INCOMPLETE","checks":{},"violations":[{"check":"SOURCE_EVIDENCE_UNAVAILABLE","count":1}]}
    missing=[key for key in CHECKS if key not in results]
    if missing:
        return {"state":"INCOMPLETE","checks":{k:int(results[k]) for k in CHECKS if k in results},"violations":[{"check":"MISSING_CHECK_EVIDENCE","missing":missing}]}
    violations=[{"check":k,"count":int(results.get(k,0))} for k in CHECKS if int(results.get(k,0))]
    return {"state":"PASS" if not violations else "FAIL","checks":{k:int(results.get(k,0)) for k in CHECKS},"violations":violations}
