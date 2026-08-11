from dataclasses import dataclass
from enum import Enum

class StrEnum(str, Enum):
    def __str__(self): return self.value


class AccountState(StrEnum):
    PENDING = "PENDING"; ACTIVE = "ACTIVE"; RESTRICTED = "RESTRICTED"; SUSPENDED = "SUSPENDED"; CLOSED = "CLOSED"


class KycState(StrEnum):
    NOT_STARTED = "NOT_STARTED"; PENDING = "PENDING"; IN_REVIEW = "IN_REVIEW"; APPROVED = "APPROVED"; REJECTED = "REJECTED"; EXPIRED = "EXPIRED"; REQUIRES_UPDATE = "REQUIRES_UPDATE"


class AmlState(StrEnum):
    NOT_SCREENED = "NOT_SCREENED"; PENDING = "PENDING"; CLEARED = "CLEARED"; REVIEW_REQUIRED = "REVIEW_REQUIRED"; BLOCKED = "BLOCKED"


class SanctionsState(StrEnum):
    NOT_CHECKED = "NOT_CHECKED"; CLEAR = "CLEAR"; POSSIBLE_MATCH = "POSSIBLE_MATCH"; CONFIRMED_MATCH = "CONFIRMED_MATCH"; MANUAL_REVIEW = "MANUAL_REVIEW"


class JurisdictionState(StrEnum):
    SUPPORTED = "SUPPORTED"; LIMITED = "LIMITED"; RESTRICTED = "RESTRICTED"; UNKNOWN = "UNKNOWN"


class EligibilityResult(StrEnum):
    ALLOWED = "ALLOWED"; DENIED = "DENIED"; REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RestrictionType(StrEnum):
    TRADING_DISABLED = "TRADING_DISABLED"; DEPOSITS_DISABLED = "DEPOSITS_DISABLED"; WITHDRAWALS_DISABLED = "WITHDRAWALS_DISABLED"; TRANSFERS_DISABLED = "TRANSFERS_DISABLED"; MARKET_DATA_LIMITED = "MARKET_DATA_LIMITED"; ACCOUNT_READ_ONLY = "ACCOUNT_READ_ONLY"; MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


KYC_TRANSITIONS = {
    KycState.NOT_STARTED: {KycState.PENDING},
    KycState.PENDING: {KycState.IN_REVIEW, KycState.REJECTED},
    KycState.IN_REVIEW: {KycState.APPROVED, KycState.REJECTED, KycState.REQUIRES_UPDATE},
    KycState.APPROVED: {KycState.EXPIRED, KycState.REQUIRES_UPDATE},
    KycState.REJECTED: {KycState.PENDING},
    KycState.EXPIRED: {KycState.PENDING, KycState.REQUIRES_UPDATE},
    KycState.REQUIRES_UPDATE: {KycState.PENDING, KycState.IN_REVIEW},
}


@dataclass(frozen=True)
class EligibilityDecisionValue:
    result: EligibilityResult
    reason_codes: tuple[str, ...]
    policy_version: str
    evaluated_at: object


# Compatibility aliases; not authoritative.
KycStatus = KycState
ScreeningStatus = AmlState
