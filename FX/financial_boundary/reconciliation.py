from enum import Enum
from collections import Counter
from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import re

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


@dataclass(frozen=True)
class ReconciliationEvidence:
    application_operations: tuple[dict, ...] = ()
    financial_operations: tuple[dict, ...] = ()
    reservations: tuple[dict, ...] = ()
    application_settlements: tuple[dict, ...] = ()
    financial_settlements: tuple[dict, ...] = ()
    wallet_projections: tuple[dict, ...] = ()
    wallet_snapshots: tuple[dict, ...] = ()
    application_deposits: tuple[dict, ...] = ()
    financial_deposits: tuple[dict, ...] = ()
    application_withdrawals: tuple[dict, ...] = ()
    financial_withdrawals: tuple[dict, ...] = ()
    application_transfers: tuple[dict, ...] = ()
    financial_transfers: tuple[dict, ...] = ()
    outbox: tuple[dict, ...] = ()
    received_events: tuple[dict, ...] = ()
    inbox: tuple[dict, ...] = ()
    audits: tuple[dict, ...] = ()

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, tuple) or not all(isinstance(item, dict) for item in value):
                raise TypeError(f"{field.name} must be a tuple of evidence objects")


@dataclass(frozen=True)
class ReconciliationFinding:
    violation: Violation
    reference: str
    evidence_hash: str
    severity: str = "CRITICAL"


@dataclass(frozen=True)
class ReconciliationReport:
    findings: tuple[ReconciliationFinding, ...]
    checks_executed: tuple[Violation, ...]
    generated_at: datetime
    evidence_hash: str

    @property
    def activation_ready(self):
        return not self.findings

    @property
    def critical_count(self):
        return sum(finding.severity == "CRITICAL" for finding in self.findings)


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _groups(items, key="reference"):
    grouped = {}
    for item in items:
        reference = str(item.get(key, ""))
        if not reference:
            raise ValueError(f"reconciliation evidence is missing {key}")
        grouped.setdefault(reference, []).append(item)
    return grouped


def _single_index(items, key="reference"):
    return {reference: rows[-1] for reference, rows in _groups(items, key).items()}


def _same(left, right, keys):
    return all(left.get(key) == right.get(key) for key in keys)


def reconcile_financial_boundary(evidence: ReconciliationEvidence, *, as_of=None) -> ReconciliationReport:
    """Compare immutable evidence only. This function has no repair or write API."""
    as_of = as_of or datetime.now(timezone.utc)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    findings = {}

    def add(violation, reference, source):
        key = (violation, str(reference))
        if key not in findings:
            finding = ReconciliationFinding(violation, str(reference), _canonical_hash(source))
            findings[key] = finding
            RECONCILIATION_VIOLATIONS.labels(violation=violation.value).inc()

    app_ops = _single_index(evidence.application_operations)
    financial_groups = _groups(evidence.financial_operations)
    financial_ops = {reference: rows[-1] for reference, rows in financial_groups.items()}
    for reference, operation in app_ops.items():
        if operation.get("requires_financial_operation", True) and reference not in financial_ops:
            add(Violation.MISSING_FINANCIAL_OPERATION, reference, operation)
    effect_ids = Counter(
        str(row["effect_id"]) for row in evidence.financial_operations if row.get("effect_id")
    )
    for reference, rows in financial_groups.items():
        if len(rows) > 1 or any(row.get("effect_id") and effect_ids[str(row["effect_id"])] > 1 for row in rows):
            add(Violation.DUPLICATE_FINANCIAL_EFFECT, reference, rows)

    terminal_states = {"FAILED", "CANCELLED", "REJECTED", "COMPLETED"}
    for reservation in evidence.reservations:
        reference = str(reservation["reference"])
        order_ref = str(reservation.get("order_ref", ""))
        owner = app_ops.get(order_ref)
        if owner is None or (reservation.get("tenant_ref") and owner.get("tenant_ref") != reservation.get("tenant_ref")):
            add(Violation.ORPHAN_RESERVATION, reference, reservation)
            continue
        state = reservation.get("state")
        expires_at = reservation.get("expires_at")
        expired = False
        if expires_at:
            parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("reservation expires_at must be timezone-aware")
            expired = parsed <= as_of
        if state in {"PENDING", "ACTIVE", "PARTIALLY_CONSUMED"} and (expired or owner.get("state") in terminal_states):
            add(Violation.RESERVATION_LEAK, reference, reservation)

    app_settlements = _single_index(evidence.application_settlements)
    financial_settlements = _single_index(evidence.financial_settlements)
    settlement_keys = ("trade_ref", "reservation_ref", "state", "asset_legs", "fee_components")
    for reference in sorted(set(app_settlements) | set(financial_settlements)):
        left, right = app_settlements.get(reference), financial_settlements.get(reference)
        if left is None or right is None or not _same(left, right, settlement_keys):
            add(Violation.SETTLEMENT_MISMATCH, reference, {"application": left, "financial": right})

    projections = _single_index(evidence.wallet_projections)
    snapshots = _single_index(evidence.wallet_snapshots)
    wallet_keys = ("asset", "total", "available", "reserved", "pending", "version")
    for reference in sorted(set(projections) | set(snapshots)):
        left, right = projections.get(reference), snapshots.get(reference)
        if left is None or right is None or not _same(left, right, wallet_keys):
            add(Violation.WALLET_PROJECTION_MISMATCH, reference, {"application": left, "financial": right})

    def compare_domain(application, financial, violation, keys=("state",)):
        left_index, right_index = _single_index(application), _single_index(financial)
        for reference in sorted(set(left_index) | set(right_index)):
            left, right = left_index.get(reference), right_index.get(reference)
            if left is None or right is None or not _same(left, right, keys):
                add(violation, reference, {"application": left, "financial": right})

    compare_domain(
        evidence.application_deposits, evidence.financial_deposits,
        Violation.DEPOSIT_CREDIT_MISMATCH, ("state", "credited_amount", "asset"),
    )
    compare_domain(evidence.application_withdrawals, evidence.financial_withdrawals, Violation.WITHDRAWAL_STATE_MISMATCH)
    compare_domain(evidence.application_transfers, evidence.financial_transfers, Violation.TRANSFER_STATE_MISMATCH)

    audit_pairs = {(str(row.get("reference")), row.get("action")) for row in evidence.audits}
    outbox_refs = {str(row.get("reference")) for row in evidence.outbox}
    inbox_ids = {str(row.get("event_id")) for row in evidence.inbox}
    for reference, operation in app_ops.items():
        audit_action = operation.get("audit_action")
        if audit_action and (reference, audit_action) not in audit_pairs:
            add(Violation.AUDIT_GAP, reference, operation)
        if operation.get("outbox_required") and reference not in outbox_refs:
            add(Violation.AUDIT_GAP, reference, operation)
    for event in evidence.received_events:
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id not in inbox_ids:
            add(Violation.AUDIT_GAP, event_id or "missing-event-id", event)

    ordered = tuple(findings[key] for key in sorted(findings, key=lambda item: (item[0].value, item[1])))
    checks = tuple(Violation)
    report_hash = _canonical_hash([
        {"violation": finding.violation.value, "reference": finding.reference, "evidence_hash": finding.evidence_hash}
        for finding in ordered
    ])
    return ReconciliationReport(ordered, checks, as_of, report_hash)


def build_reconciliation_incident(report: ReconciliationReport, *, candidate_sha: str, environment: str) -> dict:
    """Return safe immutable incident evidence; persistence is an explicit separate step."""
    if report.activation_ready:
        raise ValueError("a clean reconciliation report does not create an incident")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("candidate_sha must be a full lowercase Git SHA")
    if not re.fullmatch(r"[a-z0-9_-]{2,24}", environment):
        raise ValueError("environment is invalid")
    return {
        "severity": "CRITICAL",
        "type": "FINANCIAL_RECONCILIATION_FAILURE",
        "candidate_sha": candidate_sha,
        "environment": environment,
        "safe_summary": f"{report.critical_count} reconciliation violation(s); activation blocked",
        "status": "OPEN",
        "evidence_hash": report.evidence_hash,
    }


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
