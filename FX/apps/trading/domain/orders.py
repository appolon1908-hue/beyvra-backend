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
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
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
    OrderState.PENDING_SUBMIT: {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.ACKNOWLEDGED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING},
    OrderState.CANCEL_PENDING: {OrderState.CANCELED},
    OrderState.UNKNOWN: {OrderState.RECONCILIATION_REQUIRED, OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.FILLED, OrderState.CANCELED},
    OrderState.RECONCILIATION_REQUIRED: {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.FILLED, OrderState.CANCELED},
}
TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED, OrderState.EXPIRED}
LEGACY_STATE_ALIASES = {
    "PENDING": OrderState.PENDING_SUBMIT,
    "ACCEPTED": OrderState.ACKNOWLEDGED,
    "OPEN": OrderState.ACKNOWLEDGED,
    "CANCELLED": OrderState.CANCELED,
}


class InvalidOrderTransition(ValueError):
    pass


def transition_order(current, target):
    current = LEGACY_STATE_ALIASES.get(str(current), current)
    target = LEGACY_STATE_ALIASES.get(str(target), target)
    current, target = OrderState(current), OrderState(target)
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidOrderTransition(f"ORDER_INVALID_STATE:{current}->{target}")
    return target
