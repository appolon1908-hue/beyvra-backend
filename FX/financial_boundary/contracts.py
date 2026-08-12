from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import re


ASSET_RE = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")


class ContractError(ValueError):
    code = "VALIDATION_ERROR"


def canonical_amount(value: object, *, precision: int = 8, allow_zero: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError("amount must be a decimal string")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ContractError("amount is not a decimal") from None
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise ContractError("amount must be finite and positive")
    decimals = max(0, -amount.as_tuple().exponent)
    if decimals > precision:
        raise ContractError("amount exceeds supported precision")
    return format(amount, "f")


def canonical_asset(value: object) -> str:
    if not isinstance(value, str) or not ASSET_RE.fullmatch(value):
        raise ContractError("unsupported asset code")
    return value


@dataclass(frozen=True)
class Money:
    amount: str
    asset: str
    precision: int = 8

    def __post_init__(self):
        object.__setattr__(self, "amount", canonical_amount(self.amount, precision=self.precision, allow_zero=True))
        object.__setattr__(self, "asset", canonical_asset(self.asset))


class DepositState(str, Enum):
    CREATED = "CREATED"
    AWAITING_FUNDING = "AWAITING_FUNDING"
    DETECTED = "DETECTED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"
    CREDIT_PENDING = "CREDIT_PENDING"
    CREDITED = "CREDITED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"


class WithdrawalState(str, Enum):
    CREATED = "CREATED"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    PENDING_COMPLIANCE = "PENDING_COMPLIANCE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class TransferState(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


DEPOSIT_TRANSITIONS = {
    DepositState.CREATED: {DepositState.AWAITING_FUNDING, DepositState.CANCELLED},
    DepositState.AWAITING_FUNDING: {DepositState.DETECTED, DepositState.FAILED, DepositState.CANCELLED},
    DepositState.DETECTED: {DepositState.PENDING_CONFIRMATION, DepositState.COMPLIANCE_REVIEW, DepositState.FAILED},
    DepositState.PENDING_CONFIRMATION: {DepositState.COMPLIANCE_REVIEW, DepositState.CREDIT_PENDING, DepositState.FAILED},
    DepositState.COMPLIANCE_REVIEW: {DepositState.CREDIT_PENDING, DepositState.FAILED},
    DepositState.CREDIT_PENDING: {DepositState.CREDITED, DepositState.FAILED},
    DepositState.CREDITED: {DepositState.REVERSED},
}
WITHDRAWAL_TRANSITIONS = {
    WithdrawalState.CREATED: {WithdrawalState.PENDING_VALIDATION, WithdrawalState.CANCELLED},
    WithdrawalState.PENDING_VALIDATION: {WithdrawalState.PENDING_COMPLIANCE, WithdrawalState.REJECTED, WithdrawalState.CANCELLED},
    WithdrawalState.PENDING_COMPLIANCE: {WithdrawalState.PENDING_APPROVAL, WithdrawalState.APPROVED, WithdrawalState.REJECTED, WithdrawalState.CANCELLED},
    WithdrawalState.PENDING_APPROVAL: {WithdrawalState.APPROVED, WithdrawalState.REJECTED, WithdrawalState.CANCELLED},
    WithdrawalState.APPROVED: {WithdrawalState.QUEUED, WithdrawalState.CANCELLED},
    WithdrawalState.QUEUED: {WithdrawalState.SUBMITTED, WithdrawalState.CANCELLED, WithdrawalState.FAILED},
    WithdrawalState.SUBMITTED: {WithdrawalState.PENDING_CONFIRMATION, WithdrawalState.FAILED},
    WithdrawalState.PENDING_CONFIRMATION: {WithdrawalState.COMPLETED, WithdrawalState.FAILED},
    WithdrawalState.COMPLETED: {WithdrawalState.REVERSED},
}
TRANSFER_TRANSITIONS = {
    TransferState.CREATED: {TransferState.VALIDATING, TransferState.CANCELLED},
    TransferState.VALIDATING: {TransferState.PENDING, TransferState.FAILED, TransferState.CANCELLED},
    TransferState.PENDING: {TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED},
}


def assert_transition(current, target, transitions):
    if target not in transitions.get(current, set()):
        raise ContractError(f"invalid transition: {current} -> {target}")


@dataclass(frozen=True)
class WalletSnapshot:
    wallet_id: str
    account_ref: str
    asset: str
    total: str
    available: str
    reserved: str
    pending: str
    as_of: str
    version: int

    def __post_init__(self):
        object.__setattr__(self, "asset", canonical_asset(self.asset))
        for field in ("total", "available", "reserved", "pending"):
            object.__setattr__(self, field, canonical_amount(getattr(self, field), allow_zero=True))
        if self.version < 0:
            raise ContractError("wallet version must be non-negative")
