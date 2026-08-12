class DependencyFailureEvaluator:
    @staticmethod
    def evaluate(policy,healthy):
        return {"mode":"HEALTHY","allowed":True} if healthy else {"mode":policy.allowed_mode,"allowed":not policy.fail_closed,"fallback":policy.fallback}
