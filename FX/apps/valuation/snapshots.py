import hashlib
import json
from decimal import Decimal

from django.db.models import Sum

from .common import POLICY_VERSION, audit
from .models import RealizedPnLEvent, UnrealizedPnLSnapshot, ValuationSnapshot


class ValuationSnapshotService:
    @staticmethod
    def create(*, nav, market_data_cutoff):
        unrealized = UnrealizedPnLSnapshot.objects.filter(tenant_ref=nav.tenant_ref, account_ref=nav.account_ref, valuation_time__lte=nav.valuation_time).aggregate(v=Sum("unrealized_pnl"))["v"] or Decimal("0")
        realized = RealizedPnLEvent.objects.filter(tenant_ref=nav.tenant_ref, account_ref=nav.account_ref, realized_at__lte=nav.valuation_time).aggregate(v=Sum("realized_pnl"))["v"] or Decimal("0")
        evidence = {"nav": str(nav.id), "market_data_cutoff": market_data_cutoff.isoformat(), "policy": POLICY_VERSION}
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        row = ValuationSnapshot.objects.create(tenant_ref=nav.tenant_ref, scope_type="ACCOUNT", scope_ref=nav.account_ref, valuation_time=nav.valuation_time, base_currency=nav.base_currency, market_data_cutoff=market_data_cutoff, policy_versions={"valuation": POLICY_VERSION}, position_count=0, cash_value=nav.cash_value, position_value=nav.position_value, nav=nav.nav, realized_pnl=realized, unrealized_pnl=unrealized, quality_state=nav.quality_state, evidence_hash=digest)
        audit(tenant_ref=nav.tenant_ref, action="valuation.snapshot.created", resource=row, evidence=evidence)
        return row

