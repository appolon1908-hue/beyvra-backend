from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    quantity: Decimal
    price: Decimal
