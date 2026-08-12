REQUIRED_GATES=("exact_candidate","ci","security","migration","configuration","backup","readiness","smoke")
def evaluate_gates(results):return {"passed":all(results.get(x) is True for x in REQUIRED_GATES),"failed":[x for x in REQUIRED_GATES if results.get(x) is not True]}
def deployment_allowed(environment,results):return environment!="PRODUCTION" and evaluate_gates(results)["passed"]
