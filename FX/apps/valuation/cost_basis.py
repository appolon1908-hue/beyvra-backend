from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .common import POLICY_VERSION
from .models import CostBasisAdjustment, CostBasisPosition, TaxLot


class CostBasisService:
    @classmethod
    def calculate(cls, *, tenant_ref, account_ref, instrument_id):
        lots = TaxLot.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id, remaining_quantity__gt=0)
        quantity = lots.aggregate(v=Sum("remaining_quantity"))["v"] or Decimal("0")
        gross = sum((lot.remaining_quantity * lot.unit_cost for lot in lots), Decimal("0"))
        adjustments = CostBasisAdjustment.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id).aggregate(v=Sum("basis_delta"))["v"] or Decimal("0")
        total = gross + adjustments
        obj, _ = CostBasisPosition.objects.update_or_create(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id, defaults={"quantity": quantity, "gross_cost": gross, "allocated_fees": Decimal("0"), "adjustments": adjustments, "total_cost_basis": total, "average_unit_cost": total / quantity if quantity else Decimal("0"), "currency": lots.first().currency if lots.exists() else "USD", "policy_version": POLICY_VERSION, "as_of": timezone.now()})
        return obj

    rebuild_from_history = calculate

    @staticmethod
    def validate(position):
        if position.quantity < 0 or position.total_cost_basis < 0:
            raise ValueError("COST_BASIS_INVALID")
        return True

