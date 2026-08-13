from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Position:
    position_id: str
    instrument_id: str
    quantity: Decimal
