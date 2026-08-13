from django.utils import timezone
from apps.trading.models import ExecutionProviderHealth


class ProviderHealthService:
    def evaluate(self, provider):
        row, _ = ExecutionProviderHealth.objects.get_or_create(provider=provider, defaults={"state":provider.health})
        if not provider.enabled: return "DISABLED"
        if provider.health == "HALTED": return "HALTED"
        if row.circuit_state == "OPEN" or provider.circuit_open_until and provider.circuit_open_until > timezone.now(): return "UNAVAILABLE"
        if row.error_rate >= 0.25 or row.reject_rate >= 0.35: return "DEGRADED"
        return row.state if row.state in {"HEALTHY","DEGRADED","UNAVAILABLE","HALTED"} else "UNKNOWN"

    def is_routable(self, provider): return self.evaluate(provider) == "HEALTHY"

    def record_failure(self, provider):
        provider.consecutive_failures += 1
        if provider.consecutive_failures >= 3:
            provider.health="UNAVAILABLE"; provider.circuit_open_until=timezone.now()+__import__("datetime").timedelta(seconds=30)
        provider.save(update_fields=("consecutive_failures","health","circuit_open_until","updated_at"))
        row,_=ExecutionProviderHealth.objects.get_or_create(provider=provider); row.state=provider.health; row.circuit_state="OPEN" if provider.consecutive_failures>=3 else "CLOSED"; row.last_failure_at=timezone.now(); row.save()
        return row

    def half_open(self, provider):
        row,_=ExecutionProviderHealth.objects.get_or_create(provider=provider); row.circuit_state="HALF_OPEN"; row.save(update_fields=("circuit_state","last_checked_at")); return row

    def record_success(self, provider):
        provider.consecutive_failures=0; provider.health="HEALTHY"; provider.circuit_open_until=None; provider.save()
        row,_=ExecutionProviderHealth.objects.get_or_create(provider=provider); row.state="HEALTHY"; row.circuit_state="CLOSED"; row.last_success_at=timezone.now(); row.save(); return row
