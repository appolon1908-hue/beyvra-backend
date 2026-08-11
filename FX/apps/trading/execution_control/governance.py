from django.conf import settings


class ExecutionProviderGovernance:
    APPROVED_PAPER_STATES = {"PAPER_APPROVED", "PAPER_TECHNICALLY_CERTIFIED"}

    def reasons(self, provider, mode):
        reasons=[]
        if settings.ALL_EXECUTION_HALTED: reasons.append("ALL_EXECUTION_HALTED")
        if settings.REAL_TRADING_ENABLED or settings.EXTERNAL_EXECUTION_ENABLED or settings.LIVE_BROKER_ROUTING_ENABLED: reasons.append("LIVE_EXECUTION_DISABLED")
        if mode == "LIVE": reasons.append("LIVE_MODE_PROHIBITED")
        if not provider.enabled: reasons.append("PROVIDER_DISABLED")
        if provider.health not in {"HEALTHY"}: reasons.append("PROVIDER_UNHEALTHY")
        if provider.environment != mode: reasons.append("ENVIRONMENT_MISMATCH")
        if mode == "PAPER" and provider.governance_state not in self.APPROVED_PAPER_STATES: reasons.append("PAPER_NOT_APPROVED")
        if provider.live_supported or provider.governance_state == "LIVE_APPROVED": reasons.append("LIVE_CAPABILITY_PROHIBITED")
        return reasons

    def eligible(self, provider, mode): return not self.reasons(provider, mode)
