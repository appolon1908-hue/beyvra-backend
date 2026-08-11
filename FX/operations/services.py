import csv
import hashlib
import io
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .metrics import notification_dead_letter, notifications_created, notifications_failed
from .models import AccountFreeze, AuditEvent, Notification, OperatorActionRequest, OutboxEvent, ProcessedEvent

REASON_CODES = frozenset(
    {
        "NEW_DEVICE",
        "NEW_NETWORK",
        "TOO_MANY_FAILED_LOGINS",
        "RECENT_PASSWORD_RESET",
        "RECENT_MFA_RESET",
        "SESSION_RISK",
        "VELOCITY_EXCEEDED",
        "ACCOUNT_REVIEW_REQUIRED",
        "ACCOUNT_FROZEN",
        "HIGH_RISK_ACTION",
    }
)
SECURITY_MANDATORY = frozenset(
    {
        "NEW_DEVICE",
        "PASSWORD_CHANGED",
        "MFA_CHANGED",
        "EMAIL_CHANGED",
        "SESSION_REVOKED",
        "ACCOUNT_FROZEN",
        "HIGH_RISK_ACTION",
    }
)
REAL_FEATURE_FLAGS = {
    "REAL_WALLET_READ_ENABLED": False,
    "REAL_DEPOSITS_ENABLED": False,
    "REAL_WITHDRAWALS_ENABLED": False,
    "REAL_INTERNAL_TRANSFERS_ENABLED": False,
    "REAL_TRADING_ENABLED": False,
    "EXTERNAL_EXECUTION_ENABLED": False,
    "REAL_MONEY_ENABLED": False,
}


def tenant_for(user):
    return (getattr(user, "brand", None) or "default").strip().lower()


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    reason_codes: tuple[str, ...]
    policy_version: str
    evaluated_at: object


def evaluate_account_risk(*, tenant_id, account, signals, policy_version="2026-08-11.1"):
    reasons = tuple(sorted(set(signals) & REASON_CODES))
    freeze = AccountFreeze.objects.filter(tenant_id=tenant_id, account=account, released_at__isnull=True).first()
    if freeze and freeze.level in {"PARTIAL", "FULL"}:
        return RiskDecision("DENY", tuple(sorted(set(reasons) | {"ACCOUNT_FROZEN"})), policy_version, timezone.now())
    if {"TOO_MANY_FAILED_LOGINS", "HIGH_RISK_ACTION"} & set(reasons):
        decision = "DENY"
    elif {"ACCOUNT_REVIEW_REQUIRED", "SESSION_RISK", "VELOCITY_EXCEEDED"} & set(reasons):
        decision = "REVIEW"
    elif {"NEW_DEVICE", "NEW_NETWORK", "RECENT_PASSWORD_RESET", "RECENT_MFA_RESET"} & set(reasons):
        decision = "STEP_UP"
    else:
        decision = "ALLOW"
    return RiskDecision(decision, reasons, policy_version, timezone.now())


def assert_sensitive_mutation_allowed(*, tenant_id, account, action):
    freeze = AccountFreeze.objects.filter(tenant_id=tenant_id, account=account, released_at__isnull=True).first()
    if not freeze or freeze.level == "NONE":
        return
    if freeze.level == "FULL" or action in {"withdrawal", "transfer", "trading", "credentials"}:
        raise PermissionError("ACCOUNT_FROZEN")


@transaction.atomic
def create_notification(*, tenant_id, account, type, category, channel, template_version, payload_safe, dedup_key):
    notification, created = Notification.objects.get_or_create(
        tenant_id=tenant_id,
        account=account,
        channel=channel,
        dedup_key=dedup_key,
        defaults={
            "type": type,
            "category": category,
            "template_version": template_version,
            "payload_safe": payload_safe,
        },
    )
    if created:
        OutboxEvent.objects.create(
            tenant_id=tenant_id, topic="notification.created", payload_safe={"notification_id": str(notification.pk)}
        )
        notifications_created.labels(category=category, channel=channel).inc()
    return notification, created


def record_delivery_failure(notification, *, transient, reason_safe, max_attempts=5):
    notification.attempts += 1
    notification.failure_reason_safe = reason_safe[:255]
    if transient and notification.attempts < max_attempts:
        notification.status = "QUEUED"
        notifications_failed.labels(category=notification.category, channel=notification.channel, result="retry").inc()
    else:
        notification.status = "FAILED"
        OutboxEvent.objects.create(
            tenant_id=notification.tenant_id,
            topic="notification.dead_letter",
            payload_safe={"notification_id": str(notification.pk), "reason": notification.failure_reason_safe},
        )
        notifications_failed.labels(
            category=notification.category, channel=notification.channel, result="dead_letter"
        ).inc()
        notification_dead_letter.labels(category=notification.category, channel=notification.channel).inc()
    notification.save(update_fields=("attempts", "failure_reason_safe", "status"))
    return notification.status


@transaction.atomic
def consume_once(*, event_id, consumer, effect):
    _, created = ProcessedEvent.objects.get_or_create(event_id=event_id, consumer=consumer)
    if not created:
        return False
    effect()
    return True


@transaction.atomic
def approve_operator_request(*, request_id, approver, approver_roles):
    request = OperatorActionRequest.objects.select_for_update().get(pk=request_id)
    if request.requested_by_id == approver.id:
        raise PermissionError("SELF_APPROVAL_FORBIDDEN")
    if request.status != "PENDING" or request.expires_at <= timezone.now():
        raise PermissionError("REQUEST_NOT_APPROVABLE")
    if not set(approver_roles) & {
        "security_manager",
        "compliance_manager",
        "financial_manager",
        "operations_manager",
        "platform_admin",
    }:
        raise PermissionError("INSUFFICIENT_ROLE")
    request.status = "APPROVED"
    request.approved_by = approver
    request.approved_at = timezone.now()
    models_update = OperatorActionRequest.objects.filter(pk=request.pk, status="PENDING").update(
        status=request.status, approved_by=approver, approved_at=request.approved_at
    )
    if models_update != 1:
        raise PermissionError("APPROVAL_RACE_LOST")
    AuditEvent.objects.create(
        tenant_id=request.tenant_id,
        actor=approver,
        role=sorted(approver_roles)[0],
        action="OPERATOR_ACTION_APPROVED",
        target=request.target_ref,
        reason=request.reason,
        request_id=request.pk,
    )
    return request


def csv_safe(value):
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def render_csv(rows, fields):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_safe(row.get(key, "")) for key in fields})
    return stream.getvalue()


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
