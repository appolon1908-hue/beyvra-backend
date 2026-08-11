import csv
import hashlib
import io
import json
import uuid
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
    ReportJob,
    SecurityEvent,
    Statement,
    SupportCase,
    TradingHalt,
    TransactionHistoryEntry,
    PrivacyExportJob,
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

ACTION_ROLE_POLICY = {
    "UNFREEZE": frozenset({"security_manager", "platform_admin"}),
    "COMPLIANCE_OVERRIDE": frozenset({"compliance_manager", "platform_admin"}),
    "FINANCIAL_OVERRIDE": frozenset({"financial_manager", "platform_admin"}),
    "WITHDRAWAL_OVERRIDE": frozenset({"financial_manager", "platform_admin"}),
    "PROVIDER_ACTIVATION": frozenset({"operations_manager", "platform_admin"}),
    "REAL_MONEY_ACTIVATION": frozenset({"platform_admin"}),
    "KILL_SWITCH_RELEASE": frozenset({"operations_manager", "platform_admin"}),
    "LEGAL_HOLD_RELEASE": frozenset({"compliance_manager", "platform_admin"}),
}


def tenant_for(user):
    return (getattr(user, "brand", None) or "default").strip().lower()


def tenant_account_q(tenant_id):
    """Match persisted accounts using the same default-tenant semantics as tenant_for."""
    normalized = tenant_id.strip().lower()
    if normalized == "default":
        return Q(brand__isnull=True) | Q(brand="") | Q(brand__iexact="default")
    return Q(brand__iexact=normalized)


def request_identity_refs(*, user, request):
    tenant_id = tenant_for(user)
    user_agent = (request.META.get("HTTP_USER_AGENT") or "unknown")[:255]
    network_address = request.META.get("REMOTE_ADDR") or "unknown"
    device_hash = hashlib.sha256(
        f"{tenant_id}:{user.pk}:{user_agent}".encode()
    ).hexdigest()
    network_hash = hashlib.sha256(
        f"{tenant_id}:{user.pk}:{network_address}".encode()
    ).hexdigest()
    return user_agent, device_hash, network_hash


@transaction.atomic
def issue_session_token_pair(*, user, request, mfa_verified=False):
    from rest_framework_simplejwt.settings import api_settings
    from users.serializers import AuthTokenObtainPairSerializer

    now = timezone.now()
    tenant_id = tenant_for(user)
    user_agent, fingerprint_hash, network_hash = request_identity_refs(
        user=user, request=request
    )
    known_network = SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=user,
        event_type__in={"LOGIN_SUCCESS", "NEW_NETWORK"},
        network_ref=network_hash,
    ).exists()
    had_network = SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=user,
        event_type__in={"LOGIN_SUCCESS", "NEW_NETWORK"},
    ).exists()
    device, new_device = DeviceIdentity.objects.get_or_create(
        tenant_id=tenant_id,
        account=user,
        fingerprint_hash=fingerprint_hash,
        defaults={
            "device_class": "MOBILE" if "mobile" in user_agent.lower() else "BROWSER",
            "risk_state": "NEW",
        },
    )
    session_lifetime = (
        min(api_settings.REFRESH_TOKEN_LIFETIME, timedelta(minutes=30))
        if user.is_staff
        else api_settings.REFRESH_TOKEN_LIFETIME
    )
    session = AccountSession.objects.create(
        tenant_id=tenant_id,
        account=user,
        expires_at=now + session_lifetime,
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
        network_ref=network_hash,
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
        network_ref=network_hash,
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
    if had_network and not known_network:
        SecurityEvent.objects.create(
            tenant_id=tenant_id,
            account=user,
            event_type="NEW_NETWORK",
            occurred_at=now,
            source="AUTH",
            risk_level="MEDIUM",
            device_ref=device.device_id,
            network_ref=network_hash,
            session_ref=session.session_id,
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
        type={
            "MFA_ENABLED": "MFA_CHANGED",
            "MFA_DISABLED": "MFA_CHANGED",
            "MFA_RESET": "MFA_CHANGED",
            "EMAIL_CHANGED": "EMAIL_CHANGED",
        }.get(event_type, "PASSWORD_CHANGED"),
        category="SECURITY",
        channel="IN_APP",
        template_version="1",
        payload_safe={"action": "review_sessions"},
        dedup_key=f"credential-change:{event_type}:{int(now.timestamp())}",
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


def evaluate_login_risk(*, account, request=None):
    """Evaluate canonical login signals and append a safe decision audit."""
    tenant_id = tenant_for(account)
    now = timezone.now()
    signals = set()
    if SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=account,
        event_type="LOGIN_FAILURE",
        risk_level__in={"HIGH", "CRITICAL"},
        occurred_at__gte=now - timedelta(minutes=10),
    ).exists():
        signals.add("TOO_MANY_FAILED_LOGINS")
    if SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=account,
        event_type="PASSWORD_RESET",
        occurred_at__gte=now - timedelta(hours=24),
    ).exists():
        signals.add("RECENT_PASSWORD_RESET")
    if SecurityEvent.objects.filter(
        tenant_id=tenant_id,
        account=account,
        event_type="MFA_RESET",
        occurred_at__gte=now - timedelta(hours=24),
    ).exists():
        signals.add("RECENT_MFA_RESET")
    if request is not None:
        _, device_hash, network_hash = request_identity_refs(
            user=account, request=request
        )
        if DeviceIdentity.objects.filter(
            tenant_id=tenant_id, account=account
        ).exists() and not DeviceIdentity.objects.filter(
            tenant_id=tenant_id,
            account=account,
            fingerprint_hash=device_hash,
            revoked=False,
        ).exists():
            signals.add("NEW_DEVICE")
        prior_networks = SecurityEvent.objects.filter(
            tenant_id=tenant_id,
            account=account,
            event_type__in={"LOGIN_SUCCESS", "NEW_NETWORK"},
        )
        if prior_networks.exists() and not prior_networks.filter(
            network_ref=network_hash
        ).exists():
            signals.add("NEW_NETWORK")
    decision = evaluate_account_risk(
        tenant_id=tenant_id, account=account, signals=signals
    )
    AuditEvent.objects.create(
        tenant_id=tenant_id,
        actor=account,
        role="account",
        action="ACCOUNT_RISK_EVALUATED",
        target=f"account:{account.pk}",
        metadata_safe={
            "decision": decision.decision,
            "reason_codes": list(decision.reason_codes),
            "policy_version": decision.policy_version,
        },
    )
    return decision


def assert_sensitive_mutation_allowed(*, tenant_id, account, action):
    if action == "trading" and TradingHalt.objects.filter(
        tenant_id=tenant_id, released_at__isnull=True
    ).exists():
        raise PermissionError("TRADING_HALTED")
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
        event = OutboxEvent.objects.create(
            tenant_id=tenant_id,
            topic="notification.created",
            payload_safe={"notification_id": str(notification.pk)},
        )
        from .tasks import deliver_notification_outbox_event

        transaction.on_commit(
            lambda: deliver_notification_outbox_event.delay(str(event.event_id))
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
def approve_operator_request(
    *, request_id, tenant_id, approver, approver_roles
):
    request = OperatorActionRequest.objects.select_for_update().get(
        pk=request_id, tenant_id=tenant_id
    )
    if request.requested_by_id == approver.id:
        raise PermissionError("SELF_APPROVAL_FORBIDDEN")
    if request.status != "PENDING" or request.expires_at <= timezone.now():
        raise PermissionError("REQUEST_NOT_APPROVABLE")
    allowed_roles = ACTION_ROLE_POLICY.get(request.action_type, frozenset())
    if not set(approver_roles) & allowed_roles:
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
def execute_operator_request(
    *, request_id, tenant_id, executor, executor_roles
):
    request = OperatorActionRequest.objects.select_for_update().get(
        pk=request_id, tenant_id=tenant_id
    )
    if request.status != "APPROVED" or not request.approved_by_id:
        raise PermissionError("REQUEST_NOT_EXECUTABLE")
    if request.requested_by_id == executor.id:
        raise PermissionError("MAKER_CANNOT_EXECUTE")
    if request.action_type not in {
        "UNFREEZE",
        "KILL_SWITCH_RELEASE",
        "LEGAL_HOLD_RELEASE",
    }:
        raise PermissionError("EXTERNAL_AUTHORITY_REQUIRED")
    if not set(executor_roles) & ACTION_ROLE_POLICY[request.action_type]:
        raise PermissionError("INSUFFICIENT_ROLE")
    if request.action_type == "KILL_SWITCH_RELEASE":
        prefix, separator, raw_halt_id = request.target_ref.partition(":")
        if prefix != "trading_halt" or not separator:
            raise PermissionError("INVALID_TARGET")
        try:
            halt = TradingHalt.objects.select_for_update().get(
                halt_id=raw_halt_id,
                tenant_id=request.tenant_id,
                released_at__isnull=True,
            )
        except (ValueError, TradingHalt.DoesNotExist) as exc:
            raise PermissionError("INVALID_TARGET") from exc
        before_hash = stable_hash({"active": True, "reason": halt.reason})
        halt.released_at = timezone.now()
        halt.released_by = executor
        halt.save(update_fields=("released_at", "released_by"))
        request.status = "EXECUTED"
        request.executed_at = timezone.now()
        updated = OperatorActionRequest.objects.filter(
            pk=request.pk, tenant_id=request.tenant_id, status="APPROVED"
        ).update(status="EXECUTED", executed_at=request.executed_at)
        if updated != 1:
            raise PermissionError("EXECUTION_RACE_LOST")
        AuditEvent.objects.create(
            tenant_id=request.tenant_id,
            actor=executor,
            role="operations_manager",
            action="TRADING_HALT_RELEASED",
            target=request.target_ref,
            reason=request.reason,
            request_id=request.pk,
            before_state_hash=before_hash,
            after_state_hash=stable_hash({"active": False, "reason": halt.reason}),
        )
        return request

    if request.action_type == "LEGAL_HOLD_RELEASE":
        prefix, separator, raw_hold_id = request.target_ref.partition(":")
        if prefix != "legal_hold" or not separator:
            raise PermissionError("INVALID_TARGET")
        try:
            hold = LegalHold.objects.select_for_update().get(
                pk=raw_hold_id,
                tenant_id=request.tenant_id,
                active=True,
                released_at__isnull=True,
            )
        except (ValueError, LegalHold.DoesNotExist) as exc:
            raise PermissionError("INVALID_TARGET") from exc
        before_hash = stable_hash({"active": True, "reason": hold.reason})
        hold.active = False
        hold.released_at = timezone.now()
        hold.released_by = executor
        hold.save(update_fields=("active", "released_at", "released_by"))
        request.status = "EXECUTED"
        request.executed_at = timezone.now()
        updated = OperatorActionRequest.objects.filter(
            pk=request.pk, tenant_id=request.tenant_id, status="APPROVED"
        ).update(status="EXECUTED", executed_at=request.executed_at)
        if updated != 1:
            raise PermissionError("EXECUTION_RACE_LOST")
        AuditEvent.objects.create(
            tenant_id=request.tenant_id,
            actor=executor,
            role="compliance_manager",
            action="LEGAL_HOLD_RELEASED",
            target=request.target_ref,
            reason=request.reason,
            request_id=request.pk,
            before_state_hash=before_hash,
            after_state_hash=stable_hash({"active": False, "reason": hold.reason}),
        )
        return request

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
    updated = OperatorActionRequest.objects.filter(
        pk=request.pk, tenant_id=request.tenant_id, status="APPROVED"
    ).update(status="EXECUTED", executed_at=request.executed_at)
    if updated != 1:
        raise PermissionError("EXECUTION_RACE_LOST")
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


@transaction.atomic
def issue_simulation_statement(
    *, tenant_id, account, period_start, period_end, actor, supersedes=None, reason=""
):
    if period_start >= period_end:
        raise ValueError("INVALID_STATEMENT_PERIOD")
    if TransactionHistoryEntry.objects.filter(
        tenant_id=tenant_id,
        account=account,
        occurred_at__gte=period_start,
        occurred_at__lte=period_end,
        simulation=False,
    ).exists():
        raise PermissionError("FINANCIAL_SERVICE_AUTHORITY_REQUIRED")
    checks = reconcile_operational_domains(tenant_id=tenant_id)
    if not all(check.status == "PASS" for check in checks):
        raise PermissionError("RECONCILIATION_REQUIRED")
    version = 1
    statement_id = uuid.uuid4()
    if supersedes is not None:
        if supersedes.tenant_id != tenant_id or supersedes.account_id != account.pk:
            raise PermissionError("INVALID_SUPERSEDED_STATEMENT")
        if not reason.strip():
            raise ValueError("CORRECTION_REASON_REQUIRED")
        statement_id = supersedes.statement_id
        version = supersedes.version + 1
    statement = Statement.objects.create(
        statement_id=statement_id,
        version=version,
        tenant_id=tenant_id,
        account=account,
        period_start=period_start,
        period_end=period_end,
        simulation=True,
        reconciliation_passed=True,
        supersedes=supersedes,
        correction_reason=reason[:500],
    )
    AuditEvent.objects.create(
        tenant_id=tenant_id,
        actor=actor,
        role="financial_manager" if getattr(actor, "is_staff", False) else "system",
        action="STATEMENT_SUPERSEDED" if supersedes else "STATEMENT_GENERATED",
        target=f"statement:{statement.statement_id}:v{statement.version}",
        reason=statement.correction_reason,
    )
    return statement


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
        "SUPPORT": not SupportCase.objects.filter(
            tenant_id=tenant_id,
            status__in={"RESOLVED", "CLOSED"},
            resolved_at__isnull=True,
        ).exists(),
        "REPORTING": not (
            Statement.objects.filter(
                tenant_id=tenant_id, reconciliation_passed=False
            ).exists()
            or ReportJob.objects.filter(
                tenant_id=tenant_id, status="COMPLETED", artifact_ref=""
            ).exists()
        ),
        "PRIVACY": not PrivacyExportJob.objects.filter(
            tenant_id=tenant_id, status="COMPLETED", artifact_ref=""
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
