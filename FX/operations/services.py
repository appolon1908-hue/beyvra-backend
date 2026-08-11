import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .metrics import (
    notification_dead_letter,
    notifications_created,
    notifications_failed,
)
from .models import (
    AccountFreeze,
    AccountSession,
    AuditEvent,
    DeviceIdentity,
    LegalHold,
    Notification,
    OperatorActionRequest,
    OutboxEvent,
    ProcessedEvent,
    ReconciliationCheck,
    SecurityEvent,
)

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


def tenant_account_q(tenant_id):
    """Match persisted accounts using the same default-tenant semantics as tenant_for."""
    normalized = tenant_id.strip().lower()
    if normalized == "default":
        return Q(brand__isnull=True) | Q(brand="") | Q(brand__iexact="default")
    return Q(brand__iexact=normalized)


@transaction.atomic
def issue_session_token_pair(*, user, request, mfa_verified=False):
    from rest_framework_simplejwt.settings import api_settings
    from users.serializers import AuthTokenObtainPairSerializer

    now = timezone.now()
    tenant_id = tenant_for(user)
    user_agent = (request.META.get("HTTP_USER_AGENT") or "unknown")[:255]
    fingerprint_hash = hashlib.sha256(
        f"{tenant_id}:{user.pk}:{user_agent}".encode()
    ).hexdigest()
    device, new_device = DeviceIdentity.objects.get_or_create(
        tenant_id=tenant_id,
        account=user,
        fingerprint_hash=fingerprint_hash,
        defaults={
            "device_class": "MOBILE" if "mobile" in user_agent.lower() else "BROWSER",
            "risk_state": "NEW",
        },
    )
    session = AccountSession.objects.create(
        tenant_id=tenant_id,
        account=user,
        expires_at=now + api_settings.REFRESH_TOKEN_LIFETIME,
        device_ref=device,
        auth_strength="MFA" if mfa_verified else "PASSWORD",
        mfa_verified_at=now if mfa_verified else None,
    )
    refresh = AuthTokenObtainPairSerializer.get_token(user)
    refresh["session_id"] = str(session.session_id)
    refresh["auth_strength"] = session.auth_strength
    if mfa_verified:
        refresh["mfa_verified_at"] = int(now.timestamp())
    SecurityEvent.objects.create(
        tenant_id=tenant_id,
        account=user,
        event_type="LOGIN_SUCCESS",
        occurred_at=now,
        source="AUTH",
        risk_level="LOW",
        device_ref=device.device_id,
        session_ref=session.session_id,
        metadata_safe={"auth_strength": session.auth_strength},
    )
    SecurityEvent.objects.create(
        tenant_id=tenant_id,
        account=user,
        event_type="SESSION_CREATED",
        occurred_at=now,
        source="AUTH",
        risk_level="LOW",
        device_ref=device.device_id,
        session_ref=session.session_id,
    )
    if new_device:
        SecurityEvent.objects.create(
            tenant_id=tenant_id,
            account=user,
            event_type="NEW_DEVICE",
            occurred_at=now,
            source="AUTH",
            risk_level="MEDIUM",
            device_ref=device.device_id,
            session_ref=session.session_id,
        )
        create_notification(
            tenant_id=tenant_id,
            account=user,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            payload_safe={"action": "review_sessions"},
            dedup_key=f"new-device:{device.device_id}",
        )
    access = refresh.access_token
    return {"refresh": str(refresh), "access": str(access), "session": session}


@transaction.atomic
def revoke_sessions_after_credential_change(*, user, event_type):
    now = timezone.now()
    tenant_id = tenant_for(user)
    revoked = AccountSession.objects.filter(
        tenant_id=tenant_id, account=user, revoked_at__isnull=True
    ).update(revoked_at=now)
    SecurityEvent.objects.create(
        tenant_id=tenant_id,
        account=user,
        event_type=event_type,
        occurred_at=now,
        source="AUTH",
        risk_level="MEDIUM",
        metadata_safe={"sessions_revoked": revoked},
    )
    create_notification(
        tenant_id=tenant_id,
        account=user,
        type="PASSWORD_CHANGED",
        category="SECURITY",
        channel="IN_APP",
        template_version="1",
        payload_safe={"action": "review_sessions"},
        dedup_key=f"password-changed:{int(now.timestamp())}",
    )
    return revoked


@transaction.atomic
def revoke_bound_session(*, user, session_id):
    now = timezone.now()
    tenant_id = tenant_for(user)
    updated = AccountSession.objects.filter(
        session_id=session_id,
        tenant_id=tenant_id,
        account=user,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    if not updated:
        return False
    SecurityEvent.objects.create(
        tenant_id=tenant_id,
        account=user,
        event_type="SESSION_REVOKED",
        occurred_at=now,
        source="AUTH",
        risk_level="LOW",
        session_ref=session_id,
    )
    create_notification(
        tenant_id=tenant_id,
        account=user,
        type="SESSION_REVOKED",
        category="SECURITY",
        channel="IN_APP",
        template_version="1",
        payload_safe={"action": "review_sessions"},
        dedup_key=f"session-revoked:{session_id}",
    )
    return True


def notification_group(tenant_id, account_id):
    identity = f"{tenant_id}:{account_id}".encode()
    return "private_notifications_" + hashlib.sha256(identity).hexdigest()


def record_login_failure(*, user):
    now = timezone.now()
    tenant_id = tenant_for(user)
    recent_failures = SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=user,
        event_type="LOGIN_FAILURE",
        occurred_at__gte=now - timedelta(minutes=10),
    ).count()
    risk_level = "HIGH" if recent_failures >= 4 else "MEDIUM"
    return SecurityEvent.objects.create(
        tenant_id=tenant_id,
        account=user,
        event_type="LOGIN_FAILURE",
        occurred_at=now,
        source="AUTH",
        risk_level=risk_level,
        metadata_safe={
            "reason_code": (
                "TOO_MANY_FAILED_LOGINS"
                if risk_level == "HIGH"
                else "INVALID_CREDENTIALS"
            )
        },
    )


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    reason_codes: tuple[str, ...]
    policy_version: str
    evaluated_at: object


def evaluate_account_risk(
    *, tenant_id, account, signals, policy_version="2026-08-11.1"
):
    reasons = tuple(sorted(set(signals) & REASON_CODES))
    freeze = AccountFreeze.objects.filter(
        tenant_id=tenant_id, account=account, released_at__isnull=True
    ).first()
    if freeze and freeze.level in {"PARTIAL", "FULL"}:
        return RiskDecision(
            "DENY",
            tuple(sorted(set(reasons) | {"ACCOUNT_FROZEN"})),
            policy_version,
            timezone.now(),
        )
    if {"TOO_MANY_FAILED_LOGINS", "HIGH_RISK_ACTION"} & set(reasons):
        decision = "DENY"
    elif {"ACCOUNT_REVIEW_REQUIRED", "SESSION_RISK", "VELOCITY_EXCEEDED"} & set(
        reasons
    ):
        decision = "REVIEW"
    elif {
        "NEW_DEVICE",
        "NEW_NETWORK",
        "RECENT_PASSWORD_RESET",
        "RECENT_MFA_RESET",
    } & set(reasons):
        decision = "STEP_UP"
    else:
        decision = "ALLOW"
    return RiskDecision(decision, reasons, policy_version, timezone.now())


def assert_sensitive_mutation_allowed(*, tenant_id, account, action):
    freeze = AccountFreeze.objects.filter(
        tenant_id=tenant_id, account=account, released_at__isnull=True
    ).first()
    if not freeze or freeze.level == "NONE":
        return
    if freeze.level == "FULL" or action in {
        "withdrawal",
        "transfer",
        "trading",
        "credentials",
    }:
        raise PermissionError("ACCOUNT_FROZEN")


@transaction.atomic
def create_notification(
    *,
    tenant_id,
    account,
    type,
    category,
    channel,
    template_version,
    payload_safe,
    dedup_key,
):
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
            tenant_id=tenant_id,
            topic="notification.created",
            payload_safe={"notification_id": str(notification.pk)},
        )
        notifications_created.labels(category=category, channel=channel).inc()
    return notification, created


def realtime_notification_payload(notification):
    """Allowlisted payload for the private websocket outbox publisher."""
    return {
        "notification_id": str(notification.notification_id),
        "type": notification.type,
        "category": notification.category,
        "severity": notification.severity,
        "channel": notification.channel,
        "status": notification.status,
        "created_at": notification.created_at.isoformat(),
        "payload_safe": notification.payload_safe,
    }


def publish_realtime_notification(notification):
    async_to_sync(get_channel_layer().group_send)(
        notification_group(notification.tenant_id, notification.account_id),
        {
            "type": "notification.created",
            "notification": realtime_notification_payload(notification),
        },
    )


def record_delivery_failure(notification, *, transient, reason_safe, max_attempts=5):
    notification.attempts += 1
    notification.failure_reason_safe = reason_safe[:255]
    if transient and notification.attempts < max_attempts:
        notification.status = "QUEUED"
        notifications_failed.labels(
            category=notification.category, channel=notification.channel, result="retry"
        ).inc()
    else:
        notification.status = "FAILED"
        OutboxEvent.objects.create(
            tenant_id=notification.tenant_id,
            topic="notification.dead_letter",
            payload_safe={
                "notification_id": str(notification.pk),
                "reason": notification.failure_reason_safe,
            },
        )
        notifications_failed.labels(
            category=notification.category,
            channel=notification.channel,
            result="dead_letter",
        ).inc()
        notification_dead_letter.labels(
            category=notification.category, channel=notification.channel
        ).inc()
    notification.save(update_fields=("attempts", "failure_reason_safe", "status"))
    return notification.status


class DisabledProviderAdapter:
    """Fail-closed provider contract; activation belongs to independent governance."""

    def send(self, notification):
        raise RuntimeError("PROVIDER_DISABLED")

    def schedule(self, notification, when):
        raise RuntimeError("PROVIDER_DISABLED")

    def cancel(self, notification):
        return notification.status == "QUEUED"

    def get_status(self, notification):
        return notification.status


class NotificationService:
    def __init__(self, adapter=None):
        self.adapter = adapter or DisabledProviderAdapter()

    def send(self, notification):
        return self.adapter.send(notification)

    def schedule(self, notification, when):
        return self.adapter.schedule(notification, when)

    def cancel(self, notification):
        if self.adapter.cancel(notification):
            notification.status = "FAILED"
            notification.failure_reason_safe = "cancelled"
            notification.save(update_fields=("status", "failure_reason_safe"))
            return True
        return False

    def get_status(self, notification):
        return self.adapter.get_status(notification)

    def mark_read(self, notification):
        notification.status = "READ"
        notification.read_at = timezone.now()
        notification.save(update_fields=("status", "read_at"))
        return notification


@transaction.atomic
def consume_once(*, event_id, consumer, effect):
    _, created = ProcessedEvent.objects.get_or_create(
        event_id=event_id, consumer=consumer
    )
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
    models_update = OperatorActionRequest.objects.filter(
        pk=request.pk, status="PENDING"
    ).update(
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


@transaction.atomic
def execute_operator_request(*, request_id, executor, executor_roles):
    request = OperatorActionRequest.objects.select_for_update().get(pk=request_id)
    if request.status != "APPROVED" or not request.approved_by_id:
        raise PermissionError("REQUEST_NOT_EXECUTABLE")
    if request.requested_by_id == executor.id:
        raise PermissionError("MAKER_CANNOT_EXECUTE")
    if request.action_type != "UNFREEZE":
        raise PermissionError("EXTERNAL_AUTHORITY_REQUIRED")
    if not set(executor_roles) & {"security_manager", "platform_admin"}:
        raise PermissionError("INSUFFICIENT_ROLE")
    prefix, separator, raw_account_id = request.target_ref.partition(":")
    if prefix != "account" or not separator or not raw_account_id.isdigit():
        raise PermissionError("INVALID_TARGET")
    account = (
        get_user_model()
        .objects.filter(tenant_account_q(request.tenant_id), pk=int(raw_account_id))
        .first()
    )
    if account is None:
        raise PermissionError("INVALID_TARGET")
    freeze = (
        AccountFreeze.objects.select_for_update()
        .filter(tenant_id=request.tenant_id, account=account, released_at__isnull=True)
        .first()
    )
    if freeze is None:
        raise PermissionError("NO_ACTIVE_FREEZE")
    before_hash = stable_hash(
        {"level": freeze.level, "reason_code": freeze.reason_code, "released": False}
    )
    freeze.released_at = timezone.now()
    freeze.review_evidence = {
        "operator_action_request": str(request.pk),
        "approved_by": request.approved_by_id,
    }
    freeze.save(update_fields=("released_at", "review_evidence"))
    request.status = "EXECUTED"
    request.executed_at = timezone.now()
    OperatorActionRequest.objects.filter(pk=request.pk, status="APPROVED").update(
        status="EXECUTED", executed_at=request.executed_at
    )
    AuditEvent.objects.create(
        tenant_id=request.tenant_id,
        actor=executor,
        role="security_manager",
        action="ACCOUNT_UNFROZEN",
        target=request.target_ref,
        reason=request.reason,
        request_id=request.pk,
        before_state_hash=before_hash,
        after_state_hash=stable_hash(
            {"level": freeze.level, "reason_code": freeze.reason_code, "released": True}
        ),
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
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def deletion_disposition(*, tenant_id, account):
    held = LegalHold.objects.filter(
        tenant_id=tenant_id, account=account, active=True
    ).exists()
    return {
        "blocked_by_legal_hold": held,
        "retained_categories": (
            ["financial", "audit", "compliance"]
            if not held
            else ["all_held_categories"]
        ),
        "anonymized_categories": (
            [] if held else ["contact", "support_profile", "notification_destination"]
        ),
    }


def reconcile_operational_domains(*, tenant_id):
    checks = {
        "SECURITY": not AccountFreeze.objects.filter(
            tenant_id=tenant_id, level="NONE", released_at__isnull=True
        ).exists(),
        "NOTIFICATIONS": not Notification.objects.filter(
            tenant_id=tenant_id, status="DELIVERED", delivered_at__isnull=True
        ).exists(),
        "OPERATOR": not OperatorActionRequest.objects.filter(
            tenant_id=tenant_id, status="EXECUTED", executed_at__isnull=True
        ).exists(),
    }
    return [
        ReconciliationCheck.objects.create(
            tenant_id=tenant_id,
            domain=domain,
            status="PASS" if passed else "FAIL",
            details_safe={"consistent": passed},
        )
        for domain, passed in checks.items()
    ]
