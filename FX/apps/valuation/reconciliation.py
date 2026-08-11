from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.post_trade.models import TradePositionEffect

from .common import POLICY_VERSION, audit
from .models import CostBasisPosition, PortfolioNavSnapshot, TaxLot, ValuationAudit, ValuationReconciliationRun


class ValuationReconciler:
    @classmethod
    def run(cls, *, tenant_ref="default", persist=True):
        started, violations = timezone.now(), []
        for basis in CostBasisPosition.objects.filter(tenant_ref=tenant_ref):
            lots = TaxLot.objects.filter(tenant_ref=tenant_ref, account_ref=basis.account_ref, instrument_id=basis.instrument_id).aggregate(q=Sum("remaining_quantity"))["q"] or Decimal("0")
            effects = TradePositionEffect.objects.filter(trade__tenant_ref=tenant_ref, account_ref=basis.account_ref, instrument_id=basis.instrument_id).aggregate(q=Sum("quantity_delta"))["q"] or Decimal("0")
            if lots != basis.quantity: violations.append({"check": "TAX_LOT_QUANTITY_MISMATCH", "instrument_id": basis.instrument_id})
            if effects != basis.quantity: violations.append({"check": "POSITION_QUANTITY_MISMATCH", "instrument_id": basis.instrument_id})
        for nav in PortfolioNavSnapshot.objects.filter(tenant_ref=tenant_ref):
            if nav.total_assets - nav.total_liabilities != nav.nav: violations.append({"check": "NAV_COMPONENT_MISMATCH", "snapshot_id": str(nav.id)})
            if not ValuationAudit.objects.filter(tenant_ref=tenant_ref, resource_ref=str(nav.id)).exists(): violations.append({"check": "AUDIT_GAP", "snapshot_id": str(nav.id)})
        checks = {name: sum(v["check"] == name for v in violations) for name in ("POSITION_QUANTITY_MISMATCH", "TAX_LOT_QUANTITY_MISMATCH", "NAV_COMPONENT_MISMATCH", "AUDIT_GAP")}
        result = {"status": "PASS" if not violations else "FAIL", "checks": checks, "violations": violations}
        if persist:
            row = ValuationReconciliationRun.objects.create(tenant_ref=tenant_ref, started_at=started, completed_at=timezone.now(), status=result["status"], checks=checks, violations=violations, policy_version=POLICY_VERSION)
            audit(tenant_ref=tenant_ref, action="valuation.reconciliation.run", resource=row, evidence=result)
            result["run_id"] = str(row.id)
        return result

