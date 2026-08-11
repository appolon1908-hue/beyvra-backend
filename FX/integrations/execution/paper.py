"""Deterministic paper adapter. It has no socket/HTTP/FIX implementation."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaperExecutionResult:
    provider_order_id: str
    state: str
    filled_quantity: Decimal
    average_price: Decimal | None


class PaperExecutionProvider:
    mode = "PAPER"
    outbound_live_requests = 0

    def __init__(self, provider_id, prices):
        if not str(provider_id).startswith("paper-"):
            raise ValueError("PAPER_PROVIDER_ID_REQUIRED")
        self.provider_id = provider_id
        self.prices = {key: Decimal(str(value)) for key, value in prices.items()}

    def capabilities(self):
        return {"mode": "PAPER", "network": False, "submit": True, "cancel": True, "replace": False}

    def preview_order(self, order):
        price = self.prices.get(order.instrument_id)
        if price is None: raise ValueError("INSTRUMENT_UNSUPPORTED")
        return {"provider_id": self.provider_id, "reference_price": str(price), "financial_effects": 0}

    def submit_order(self, order):
        price = self.prices.get(order.instrument_id)
        if price is None: raise ValueError("INSTRUMENT_UNSUPPORTED")
        return PaperExecutionResult(f"{self.provider_id}:{order.id}", "FILLED", order.quantity, price)

    def cancel_order(self, provider_order_id): return {"provider_order_id": provider_order_id, "state": "CANCELLED", "paper": True}
    def replace_order(self, *_args, **_kwargs): raise ValueError("CAPABILITY_UNSUPPORTED")
    def get_order(self, provider_order_id): return {"provider_order_id": provider_order_id, "paper": True}
    def list_orders(self, _account_ref): return []
    def get_executions(self, _provider_order_id): return []
    def health(self): return {"state": "HEALTHY", "mode": "PAPER", "outbound_live_requests": 0}
