from enum import StrEnum


class AccountStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    RESTRICTED = "RESTRICTED"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class Environment(StrEnum):
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    SANDBOX_REFERENCE = "SANDBOX_REFERENCE"


class CustodyModel(StrEnum):
    SEGREGATED = "SEGREGATED"
    OMNIBUS = "OMNIBUS"
    HYBRID = "HYBRID"
    NON_CUSTODIAL_REFERENCE = "NON_CUSTODIAL_REFERENCE"
    UNKNOWN = "UNKNOWN"


class AllocationMethod(StrEnum):
    PRO_RATA = "PRO_RATA"
    FIXED_PERCENT = "FIXED_PERCENT"
    FIXED_QUANTITY = "FIXED_QUANTITY"
    ORDER_SPECIFIED = "ORDER_SPECIFIED"
    STRATEGY_DEFINED = "STRATEGY_DEFINED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


def choices(enum):
    return [(item.value, item.value) for item in enum]
