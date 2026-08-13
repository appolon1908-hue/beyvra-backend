from prometheus_client import Counter


RECONCILIATION_VIOLATIONS = Counter(
    "beyvra_financial_reconciliation_violations_total",
    "Read-only financial reconciliation violations.",
    ("violation",),
)
WITHDRAWAL_SECURITY_DENIALS = Counter(
    "beyvra_withdrawal_security_denials_total",
    "Expected withdrawal security denials.",
    ("reason",),
)
WITHDRAWAL_STEP_UP_REQUIRED = Counter(
    "beyvra_withdrawal_step_up_required_total",
    "Withdrawal requests requiring fresh step-up authentication.",
)


WITHDRAWAL_DENIAL_REASONS = {
    "WITHDRAWAL_NOT_ALLOWED", "COMPLIANCE_REVIEW_REQUIRED", "STEP_UP_REQUIRED",
    "SECURITY_CHANGE_COOLDOWN", "DESTINATION_NOT_VERIFIED",
    "DESTINATION_COOLDOWN", "REVIEW_REQUIRED",
}


def observe_withdrawal_decision(decision):
    if decision in WITHDRAWAL_DENIAL_REASONS:
        WITHDRAWAL_SECURITY_DENIALS.labels(reason=decision).inc()
    if decision == "STEP_UP_REQUIRED":
        WITHDRAWAL_STEP_UP_REQUIRED.inc()
    return decision
