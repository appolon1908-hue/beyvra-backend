from django.db.models.signals import post_save
from django.dispatch import receiver

from .metrics import security_events, support_cases_open
from .models import SecurityEvent, SupportCase


@receiver(post_save, sender=SecurityEvent)
def observe_security_event(sender, instance, created, **kwargs):
    if not created:
        return
    reason = instance.metadata_safe.get("reason_code") or instance.event_type
    allowed_reasons = {
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
        "INVALID_CREDENTIALS",
        "LOGIN_SUCCESS",
        "SESSION_CREATED",
        "SESSION_REVOKED",
        "PASSWORD_RESET",
        "MFA_ENABLED",
        "MFA_DISABLED",
        "MFA_RESET",
        "ACCOUNT_LOCKED",
        "ACCOUNT_UNLOCKED",
        "WITHDRAWAL_ATTEMPT",
        "SUSPICIOUS_ACTIVITY",
    }
    security_events.labels(
        reason=reason if reason in allowed_reasons else "OTHER",
        risk=instance.risk_level,
    ).inc()


@receiver(post_save, sender=SupportCase)
def refresh_open_support_case_gauge(sender, **kwargs):
    support_cases_open.set(
        SupportCase.objects.exclude(status__in={"RESOLVED", "CLOSED"}).count()
    )
