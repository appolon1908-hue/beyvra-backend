try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility for local certification.
    from enum import Enum
    class StrEnum(str, Enum):
        def __str__(self): return self.value


class OrderState(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


TRANSITIONS = {
    OrderState.PENDING: {OrderState.ACCEPTED, OrderState.REJECTED},
    OrderState.ACCEPTED: {OrderState.OPEN, OrderState.CANCEL_PENDING},
    OrderState.OPEN: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCEL_PENDING},
    OrderState.CANCEL_PENDING: {OrderState.CANCELLED},
}
TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED}


class InvalidOrderTransition(ValueError):
    pass


def transition_order(current, target):
    current, target = OrderState(current), OrderState(target)
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidOrderTransition(f"ORDER_INVALID_STATE:{current}->{target}")
    return target
