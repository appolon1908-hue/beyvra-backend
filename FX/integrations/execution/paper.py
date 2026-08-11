"""Deterministic paper adapter. It has no socket/HTTP/FIX implementation."""
from dataclasses import dataclass
from decimal import Decimal
from .provider import ExecutionProvider


@dataclass(frozen=True)
class PaperExecutionResult:
    provider_order_id: str
    state: str
    filled_quantity: Decimal
    average_price: Decimal | None


class PaperExecutionProvider(ExecutionProvider):
    mode = "PAPER"
    outbound_live_requests = 0

    def __init__(self, provider_id, prices):
        if not str(provider_id).startswith("paper-"):
            raise ValueError("PAPER_PROVIDER_ID_REQUIRED")
        self.provider_id = provider_id
        self.prices = {key: Decimal(str(value)) for key, value in prices.items()}

    def capabilities(self):
        return {"mode": "PAPER", "network": False, "submit": True, "cancel": True, "replace": True}

    def preview_order(self, order):
        price = self.prices.get(order.instrument_id)
        if price is None: raise ValueError("INSTRUMENT_UNSUPPORTED")
        return {"provider_id": self.provider_id, "reference_price": str(price), "financial_effects": 0}

    def submit_order(self, order):
        price = self.prices.get(order.instrument_id)
        if price is None: raise ValueError("INSTRUMENT_UNSUPPORTED")
        return PaperExecutionResult(f"{self.provider_id}:{order.id}", "FILLED", order.quantity, price)

    def cancel_order(self, provider_order_id): return {"provider_order_id": provider_order_id, "state": "CANCELLED", "paper": True}
    def replace_order(self, provider_order_id, changes): return {"provider_order_id":provider_order_id,"state":"REPLACED","changes":dict(changes),"paper":True}
    def get_order(self, provider_order_id): return {"provider_order_id": provider_order_id, "paper": True}
    def list_orders(self, _account_ref): return []
    def get_executions(self, _provider_order_id): return []
    def resolve_unknown_operation(self, client_order_id): return {"client_order_id":str(client_order_id),"state":"NOT_FOUND","paper":True}
    def health(self): return {"state": "HEALTHY", "mode": "PAPER", "outbound_live_requests": 0}
