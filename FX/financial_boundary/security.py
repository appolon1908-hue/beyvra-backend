from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .metrics import observe_withdrawal_decision


@dataclass(frozen=True)
class WithdrawalSecurityContext:
    account_active: bool
    kyc_approved: bool
    aml_cleared: bool
    sanctions_clear: bool
    jurisdiction_supported: bool
    frozen: bool
    session_authenticated_at: datetime | None
    mfa_authenticated_at: datetime | None
    security_changed_at: datetime | None = None
    destination_verified: bool = False
    destination_cooldown_until: datetime | None = None
    requester_ref: str = ""
    approver_ref: str = ""


@dataclass(frozen=True)
class WithdrawalPolicy:
    version: str = "withdrawal-security-v1"
    session_max_age: timedelta = timedelta(minutes=30)
    mfa_max_age: timedelta = timedelta(minutes=10)
    security_change_cooldown: timedelta = timedelta(hours=24)
    per_transaction_limit: Decimal = Decimal("10000")


def evaluate_withdrawal(context, amount: str, *, now=None, policy=WithdrawalPolicy()):
    now = now or datetime.now(timezone.utc)
    if context.frozen or not context.account_active:
        return observe_withdrawal_decision("WITHDRAWAL_NOT_ALLOWED")
    if not all((context.kyc_approved, context.aml_cleared, context.sanctions_clear, context.jurisdiction_supported)):
        return observe_withdrawal_decision("COMPLIANCE_REVIEW_REQUIRED")
    if context.session_authenticated_at is None or now - context.session_authenticated_at > policy.session_max_age:
        return observe_withdrawal_decision("STEP_UP_REQUIRED")
    if context.mfa_authenticated_at is None or now - context.mfa_authenticated_at > policy.mfa_max_age:
        return observe_withdrawal_decision("STEP_UP_REQUIRED")
    if context.security_changed_at and now - context.security_changed_at < policy.security_change_cooldown:
        return observe_withdrawal_decision("SECURITY_CHANGE_COOLDOWN")
    if not context.destination_verified:
        return observe_withdrawal_decision("DESTINATION_NOT_VERIFIED")
    if context.destination_cooldown_until and context.destination_cooldown_until > now:
        return observe_withdrawal_decision("DESTINATION_COOLDOWN")
    if Decimal(amount) > policy.per_transaction_limit:
        return observe_withdrawal_decision("REVIEW_REQUIRED")
    return "ELIGIBLE"


def assert_separation_of_duties(requester_ref, approver_ref):
    if not requester_ref or requester_ref == approver_ref:
        raise PermissionError("SELF_APPROVAL_DENIED")
