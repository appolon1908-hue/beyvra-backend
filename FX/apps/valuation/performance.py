from decimal import Decimal

from django.utils import timezone

from .common import POLICY_VERSION
from .models import PerformanceAttribution, PerformanceSnapshot, PortfolioBenchmarkAssignment


class PerformanceReturnService:
    @staticmethod
    def calculate(*, tenant_ref, account_ref, period_start, period_end, opening_value, closing_value, external_flows=Decimal("0"), income=Decimal("0"), fees=Decimal("0")):
        if opening_value <= 0:
            raise ValueError("PERFORMANCE_OPENING_VALUE_REQUIRED")
        pnl = closing_value - opening_value - external_flows
        value = pnl / opening_value
        return PerformanceSnapshot.objects.create(tenant_ref=tenant_ref, account_ref=account_ref, period_start=period_start, period_end=period_end, opening_value=opening_value, closing_value=closing_value, external_flows=external_flows, income=income, fees=fees, pnl=pnl, return_value=value, return_method="SIMPLE_RETURN", quality_state="FRESH", policy_version=POLICY_VERSION)


class PerformanceAttributionService:
    @staticmethod
    def attribute(*, performance, dimension, dimension_value, pnl_contribution, fees=Decimal("0"), income=Decimal("0")):
        return PerformanceAttribution.objects.create(tenant_ref=performance.tenant_ref, account_ref=performance.account_ref, period_start=performance.period_start, period_end=performance.period_end, dimension=dimension, dimension_value=dimension_value, opening_value=performance.opening_value, pnl_contribution=pnl_contribution, return_contribution=pnl_contribution / performance.opening_value, fees=fees, income=income, policy_version=POLICY_VERSION, quality_state=performance.quality_state)


class BenchmarkService:
    @staticmethod
    def assignment(*, tenant_ref, scope_ref, at=None):
        at = at or timezone.now()
        row = PortfolioBenchmarkAssignment.objects.filter(tenant_ref=tenant_ref, scope_ref=scope_ref, effective_from__lte=at).order_by("-effective_from").first()
        if not row or row.effective_to and row.effective_to < at:
            raise ValueError("NO_APPROVED_BENCHMARK")
        return row

