"""Deterministic execution adapter with no network or broker dependencies."""
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings


@dataclass(frozen=True)
class SimulatedExecution:
    execution_id: str
    quantity: Decimal
    price: Decimal
    final: bool
    outcome: str = "FILL"


class SimulatedExecutionProvider:
    scenarios = {"IMMEDIATE_FULL_FILL", "PARTIAL_THEN_FILL", "OPEN_THEN_CANCEL", "REJECT", "EXPIRE"}

    def __init__(self, scenario=None):
        self.scenario = scenario or settings.SIMULATED_EXECUTION_SCENARIO
        if self.scenario not in self.scenarios:
            raise ValueError("INVALID_SIMULATION_SCENARIO")

    def submit_order(self, order):
        price = Decimal(str(settings.SIMULATED_EXECUTION_PRICES[order.instrument_id]))
        prefix = f"sim:{order.id}"
        if self.scenario == "REJECT": return [SimulatedExecution(prefix + ":reject", Decimal("0"), price, True, "REJECT")]
        if self.scenario == "EXPIRE": return [SimulatedExecution(prefix + ":expire", Decimal("0"), price, True, "EXPIRE")]
        if self.scenario == "OPEN_THEN_CANCEL": return []
        if self.scenario == "PARTIAL_THEN_FILL":
            first = Decimal("4") if order.quantity == Decimal("10") else order.quantity * Decimal("0.4")
            return [SimulatedExecution(prefix + ":1", first, price, False), SimulatedExecution(prefix + ":2", order.quantity - first, price, True)]
        return [SimulatedExecution(prefix + ":1", order.quantity, price, True)]

    def cancel_order(self, provider_order_id): return {"provider_order_id": str(provider_order_id), "state": "CANCELLED", "simulated": True}
    def get_order(self, provider_order_id): return {"provider_order_id": str(provider_order_id), "simulated": True}
    def get_positions(self, account_ref): return []
    def health(self): return {"state": "HEALTHY", "simulated": True, "outbound_requests": 0}
