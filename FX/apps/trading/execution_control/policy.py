from decimal import Decimal
from django.utils import timezone
from apps.trading.models import BestExecutionPolicy


class BestExecutionPolicyAuthority:
    VERSION="best-execution-technical-v2"
    def active(self, asset_class, mode):
        row=BestExecutionPolicy.objects.filter(asset_class=asset_class,mode=mode,status="ACTIVE",effective_from__lte=timezone.now(),effective_to__isnull=True).order_by("-effective_from").first()
        if row: return row
        return BestExecutionPolicy.objects.create(code=f"fixture-{asset_class.lower()}-{mode.lower()}",asset_class=asset_class,mode=mode,
            price_weight=Decimal("0.35"),fee_weight=Decimal("0.20"),latency_weight=Decimal("0.10"),fill_probability_weight=Decimal("0.15"),
            liquidity_weight=Decimal("0.05"),reliability_weight=Decimal("0.10"),market_impact_weight=Decimal("0.05"),status="ACTIVE",policy_version=self.VERSION,effective_from=timezone.now())

    def score(self, policy, economics):
        return (economics["price_score"]*policy.price_weight + economics["fee_score"]*policy.fee_weight +
            economics["latency_score"]*policy.latency_weight + economics["fill_score"]*policy.fill_probability_weight +
            economics["liquidity_score"]*policy.liquidity_weight + economics["reliability_score"]*policy.reliability_weight +
            economics["impact_score"]*policy.market_impact_weight).quantize(Decimal("0.00000001"))
