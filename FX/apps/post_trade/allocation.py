from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .common import audit, publish
from .models import TradeAllocation
from .observability import ALLOCATIONS


class TradeAllocationService:
    @staticmethod
    def validate(trade):
        allocated = trade.allocations.aggregate(total=Sum("allocation_quantity"))["total"] or Decimal("0")
        if allocated != trade.quantity:
            raise ValueError("ALLOCATION_QUANTITY_MISMATCH")
        return True

    @classmethod
    @transaction.atomic
    def allocate(cls, trade, allocations=None):
        allocations = allocations or [{"account_ref": trade.account_ref, "quantity": trade.quantity, "method": "DIRECT_ACCOUNT"}]
        if sum((Decimal(str(row["quantity"])) for row in allocations), Decimal("0")) != trade.quantity:
            raise ValueError("ALLOCATION_QUANTITY_MISMATCH")
        result = []
        for row in allocations:
            if row["account_ref"] != trade.account_ref:
                raise ValueError("CROSS_TENANT_ALLOCATION")
            allocation, _ = TradeAllocation.objects.get_or_create(trade=trade, account_ref=row["account_ref"], subaccount_ref=row.get("subaccount_ref", ""), strategy_ref=row.get("strategy_ref", ""), defaults={"tenant_ref": trade.tenant_ref, "allocation_quantity": Decimal(str(row["quantity"])), "allocation_notional": Decimal(str(row["quantity"])) * trade.price, "allocation_method": row.get("method", "DIRECT_ACCOUNT")})
            result.append(allocation)
            transaction.on_commit(lambda method=allocation.allocation_method: ALLOCATIONS.labels(method).inc())
        cls.validate(trade)
        audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="trade.allocated", resource_type="trade", resource_ref=trade.id, evidence={"allocation_ids": [str(row.id) for row in result]})
        publish(trade=trade, event_type="trade.allocated.v1", payload={"allocation_count": len(result)})
        return result

    @staticmethod
    def get_allocations(trade):
        return trade.allocations.order_by("created_at", "id")
