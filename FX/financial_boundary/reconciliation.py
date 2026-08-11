from enum import Enum
from collections import Counter

from .metrics import RECONCILIATION_VIOLATIONS


class Violation(str, Enum):
    MISSING_FINANCIAL_OPERATION = "MISSING_FINANCIAL_OPERATION"
    DUPLICATE_FINANCIAL_EFFECT = "DUPLICATE_FINANCIAL_EFFECT"
    ORPHAN_RESERVATION = "ORPHAN_RESERVATION"
    RESERVATION_LEAK = "RESERVATION_LEAK"
    SETTLEMENT_MISMATCH = "SETTLEMENT_MISMATCH"
    WALLET_PROJECTION_MISMATCH = "WALLET_PROJECTION_MISMATCH"
    DEPOSIT_CREDIT_MISMATCH = "DEPOSIT_CREDIT_MISMATCH"
    WITHDRAWAL_STATE_MISMATCH = "WITHDRAWAL_STATE_MISMATCH"
    TRANSFER_STATE_MISMATCH = "TRANSFER_STATE_MISMATCH"
    AUDIT_GAP = "AUDIT_GAP"


def compare_records(application, authoritative):
    """Read-only comparison; this function never repairs financial state."""
    findings = []
    app_counts = Counter(item["reference"] for item in application)
    fs_counts = Counter(item["reference"] for item in authoritative)
    app_by_key = {item["reference"]: item for item in application}
    fs_by_key = {item["reference"]: item for item in authoritative}
    for key in sorted(set(app_by_key) | set(fs_by_key)):
        left, right = app_by_key.get(key), fs_by_key.get(key)
        if fs_counts[key] > 1:
            findings.append((key, Violation.DUPLICATE_FINANCIAL_EFFECT))
        elif app_counts[key] > 1:
            findings.append((key, Violation.AUDIT_GAP))
        elif left is None or right is None:
            findings.append((key, Violation.MISSING_FINANCIAL_OPERATION))
        elif left.get("state") != right.get("state"):
            findings.append((key, Violation.WITHDRAWAL_STATE_MISMATCH))
    for _, violation in findings:
        RECONCILIATION_VIOLATIONS.labels(violation=violation.value).inc()
    return findings
