import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.email_client import EmailMiddlewareError
from users.models import (
    PendingRegistration,
    PhoneVerificationCode,
    TransactionalEmailOutbox,
    User,
    UserDeviceInfo,
)

from .email_verification import send_outbox_message
from .utils import (
    send_email_verification_email,
    send_mobile_verification_code,
    send_password_reset_link_email,
    send_user_ban_email,
    send_user_device_info_alert,
    send_welcome_email,
)


logger = logging.getLogger("beyvra.transactional_email")


def _otp_delivery_identity(item):
    """Return the registration UUID and ordinal encoded in an OTP outbox key."""
    if item.template_key != "email_otp":
        return None

    key_parts = item.idempotency_key.split(":", 2)
    if len(key_parts) != 3 or key_parts[0] != "otp":
        return False
    try:
        registration_id = uuid.UUID(key_parts[1])
        send_count = int(key_parts[2])
    except (TypeError, ValueError, AttributeError):
        return False
    if send_count < 1:
        return False
    return registration_id, send_count


def _otp_delivery_is_current(item, now, *, lock=False):
    """Return whether this exact queued OTP challenge is still active.

    The outbox identity is ``otp:<registration UUID>:<send_count>``. Matching
    the ordinal prevents a delayed first-code message from being delivered
    after a resend has invalidated it and created a newer challenge.

    When ``lock`` is true, the pending-registration row is locked. The resend
    endpoint locks the same row before invalidating and replacing a challenge,
    so the worker can hold that lock through the provider transition and make
    validation plus delivery serial with resend.
    """
    identity = _otp_delivery_identity(item)
    if identity is None:
        return True
    if identity is False:
        return False
    registration_id, send_count = identity

    registrations = PendingRegistration.objects
    if lock:
        registrations = registrations.select_for_update()
    pending = registrations.filter(pk=registration_id).first()
    if (
        pending is None
        or pending.status != "pending_email_verification"
        or pending.expires_at <= now
    ):
        return False

    challenges = pending.challenges
    if lock:
        challenges = challenges.select_for_update()
    return challenges.filter(
        status="active",
        expires_at__gt=now,
        send_count=send_count,
    ).exists()


@shared_task
def async_send_welcome_email(user_email, first_name, temp_password=None):
    send_welcome_email(user_email, first_name, temp_password)


@shared_task
def async_send_email_verification_email(user_id):
    user = User.objects.get(id=user_id)
    send_email_verification_email(user)


@shared_task
def async_send_password_reset_link_email(user_id):
    user = User.objects.get(id=user_id)
    send_password_reset_link_email(user)


@shared_task
def async_send_mobile_verification_code(user_id):
    user = User.objects.get(id=user_id)
    code = send_mobile_verification_code(user)
    try:
        phone_code_instance = PhoneVerificationCode.objects.get(user=user)
        phone_code_instance.code = code
        phone_code_instance.failed_checks = 0
        phone_code_instance.save()
    except PhoneVerificationCode.DoesNotExist:
        PhoneVerificationCode.objects.create(user=user, code=code)


@shared_task
def async_send_device_verification_email(user_id):
    user = User.objects.get(id=user_id)
    user_device_info = UserDeviceInfo.objects.get(user=user)
    send_user_device_info_alert(user, user_device_info)


@shared_task
def async_send_user_ban_email(user_id):
    user = User.objects.get(id=user_id)
    print("Sending user ban email")
    send_user_ban_email(user)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_transactional_email_outbox(self):
    item = None
    try:
        # Claim only one due item. This transaction is intentionally short so
        # unrelated outbox workers are not held behind provider I/O.
        with transaction.atomic():
            now = timezone.now()
            item = (
                TransactionalEmailOutbox.objects.select_for_update(skip_locked=True)
                .filter(
                    Q(status="pending", next_attempt_at__lte=now)
                    | Q(status="processing", lease_expires_at__lt=now)
                )
                .order_by("next_attempt_at")
                .first()
            )
            if not item:
                return "empty"
            item.status = "processing"
            item.lease_expires_at = now + timedelta(minutes=2)
            item.attempt_count += 1
            item.save(
                update_fields=["status", "lease_expires_at", "attempt_count"]
            )

        # Re-lock the claimed outbox row and, for OTP mail, the associated
        # pending-registration row. Resend locks that same registration row.
        # Holding the registration lock through the bounded provider request
        # ensures a resend cannot commit between validation and delivery.
        with transaction.atomic():
            item = TransactionalEmailOutbox.objects.select_for_update().get(
                pk=item.pk
            )
            now = timezone.now()
            if not _otp_delivery_is_current(item, now, lock=True):
                item.status = "dead_letter"
                item.last_error_code = "OTP_EXPIRED_BEFORE_DELIVERY"
                item.lease_expires_at = None
                item.save(
                    update_fields=[
                        "status",
                        "last_error_code",
                        "lease_expires_at",
                    ]
                )
                logger.info(
                    "transactional_email_stale_otp_suppressed",
                    extra={
                        "outbox_id": str(item.pk),
                        "attempt_count": item.attempt_count,
                    },
                )
                return "failed"

            result = send_outbox_message(item)
            if result == "disabled":
                item.status = "pending"
                item.lease_expires_at = None
                item.next_attempt_at = timezone.now() + timedelta(minutes=5)
                item.save(
                    update_fields=[
                        "status",
                        "lease_expires_at",
                        "next_attempt_at",
                    ]
                )
                return result

            item.status = "sent"
            item.sent_at = timezone.now()
            item.provider_message_id = str(
                result.get("provider_message_id")
                or result.get("notification_id")
                or ""
            )
            item.provider_status = str(result.get("status") or "QUEUED")
            item.lease_expires_at = None
            item.last_error_code = ""
            item.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "provider_message_id",
                    "provider_status",
                    "lease_expires_at",
                    "last_error_code",
                ]
            )
            return "sent"
    except EmailMiddlewareError as exc:
        if item is not None:
            item.status = (
                "dead_letter"
                if not exc.retryable or item.attempt_count >= 5
                else "pending"
            )
            item.last_error_code = exc.error_class[:64]
            item.lease_expires_at = None
            delays = (1, 2, 10, 60, 240)
            item.next_attempt_at = timezone.now() + timedelta(
                minutes=delays[min(item.attempt_count - 1, 4)]
            )
            item.save(
                update_fields=[
                    "status",
                    "last_error_code",
                    "lease_expires_at",
                    "next_attempt_at",
                ]
            )
            logger.warning(
                "transactional_email_delivery_failed",
                extra={
                    "outbox_id": str(item.pk),
                    "error_code": item.last_error_code,
                    "attempt_count": item.attempt_count,
                },
            )
        return "failed"
    except Exception as exc:
        if item is not None:
            item.status = (
                "dead_letter" if item.attempt_count >= 5 else "pending"
            )
            item.last_error_code = type(exc).__name__[:64]
            item.lease_expires_at = None
            item.next_attempt_at = timezone.now() + timedelta(minutes=10)
            item.save(
                update_fields=[
                    "status",
                    "last_error_code",
                    "lease_expires_at",
                    "next_attempt_at",
                ]
            )
            logger.exception(
                "transactional_email_unexpected_failure",
                extra={
                    "outbox_id": str(item.pk),
                    "error_code": item.last_error_code,
                    "attempt_count": item.attempt_count,
                },
            )
        return "failed"
