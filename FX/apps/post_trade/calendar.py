from datetime import timedelta

from .models import SettlementCalendar


class SettlementCalendarService:
    @staticmethod
    def calculate_settlement_date(*, trade_date, asset_class="CRYPTO", venue_id="SIMULATED", currency="USD"):
        policy = SettlementCalendar.objects.filter(asset_class=asset_class, effective_from__lte=trade_date).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=trade_date)).order_by("-effective_from").first()
        if not policy:
            raise ValueError("SETTLEMENT_CALENDAR_UNAVAILABLE")
        days = {"INSTANT": 0, "T_PLUS_0": 0, "BLOCKCHAIN_FINALITY": 0, "T_PLUS_1": 1, "T_PLUS_2": 2}.get(policy.settlement_convention)
        if days is None:
            raise ValueError("CUSTOM_SETTLEMENT_POLICY_REQUIRED")
        result = trade_date
        holidays = set(policy.holidays)
        advanced = 0
        while advanced < days:
            result += timedelta(days=1)
            if result.weekday() < 5 and result.isoformat() not in holidays:
                advanced += 1
        return result, policy


from django.db import models  # imported last to keep the authority API prominent
