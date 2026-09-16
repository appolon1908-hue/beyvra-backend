try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility for local certification.
    from enum import Enum
    class StrEnum(str, Enum):
        def __str__(self): return self.value


class OrderState(StrEnum):
    DRAFT = "DRAFT"
    PREVIEWED = "PREVIEWED"
    PENDING_SUBMIT = "PENDING_SUBMIT"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


TRANSITIONS = {
    OrderState.DRAFT: {OrderState.PREVIEWED, OrderState.REJECTED},
    OrderState.PREVIEWED: {OrderState.PENDING_SUBMIT, OrderState.REJECTED, OrderState.EXPIRED},
    OrderState.PENDING_SUBMIT: {OrderState.ACKNOWLEDGED, OrderState.ACCEPTED, OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.PENDING: {OrderState.ACCEPTED, OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.ACCEPTED: {OrderState.OPEN, OrderState.CANCEL_PENDING, OrderState.ACKNOWLEDGED},
    OrderState.ACKNOWLEDGED: {OrderState.OPEN, OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.EXPIRED},
    OrderState.OPEN: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING},
    OrderState.CANCEL_PENDING: {OrderState.CANCELLED, OrderState.CANCELED},
    OrderState.UNKNOWN: {OrderState.RECONCILIATION_REQUIRED, OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.FILLED, OrderState.CANCELED, OrderState.CANCELLED},
    OrderState.RECONCILIATION_REQUIRED: {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.FILLED, OrderState.CANCELED, OrderState.CANCELLED},
}
TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELLED, OrderState.CANCELED, OrderState.REJECTED, OrderState.EXPIRED}


class InvalidOrderTransition(ValueError):
    pass


def transition_order(current, target):
    current, target = OrderState(current), OrderState(target)
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidOrderTransition(f"ORDER_INVALID_STATE:{current}->{target}")
    return target
