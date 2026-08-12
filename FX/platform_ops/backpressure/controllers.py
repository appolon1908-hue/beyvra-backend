class BackpressureController:
    PROTECTED=("COMMITTED_STATE","AUDIT","RISK","CUSTOMER_MUTATIONS","CUSTOMER_READS","ANALYTICS","TELEMETRY")
    @staticmethod
    def evaluate(policy,value):
        if value>=policy.critical_threshold:return policy.action
        if value>=policy.warning_threshold:return "THROTTLE"
        return "NORMAL"
    @staticmethod
    def may_drop(kind): return kind=="NONCRITICAL_TELEMETRY"
