import smtplib
import logging
from datetime import timedelta

from celery import shared_task
from users.models import PendingRegistration, PhoneVerificationCode, TransactionalEmailOutbox, User, UserDeviceInfo

from .utils import (
    send_email_verification_email,
    send_mobile_verification_code,
    send_password_reset_link_email,
    send_user_device_info_alert,
    send_welcome_email,
    send_user_ban_email,
)
from .email_verification import send_outbox_message
from django.db import transaction
from django.utils import timezone


logger = logging.getLogger("beyvra.transactional_email")


def _otp_delivery_is_current(item, now):
    if item.template_key != "email_otp":
        return True
    key_parts = item.idempotency_key.split(":", 2)
    if len(key_parts) != 3 or key_parts[0] != "otp":
        return False
    return PendingRegistration.objects.filter(
        pk=key_parts[1],
        status="pending_email_verification",
        expires_at__gt=now,
        challenges__status="active",
        challenges__expires_at__gt=now,
    ).exists()


@shared_task
def async_send_welcome_email(user_email, first_name, temp_password=None):
    send_welcome_email(user_email, first_name, temp_password)


@shared_task
def async_send_email_verification_email(user_id):
    user = User.objects.get(id=user_id)
    send_email_verification_email(user)


@shared_task(
    autoretry_for=(smtplib.SMTPException,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
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
        phone_code_instance = PhoneVerificationCode.objects.create(user=user, code=code)


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


@shared_task
def process_transactional_email_outbox(batch_size=25):
    results = {"sent": 0, "failed": 0, "disabled": 0}
    for _ in range(max(1, min(int(batch_size), 100))):
        item = None
        try:
            with transaction.atomic():
                item = (
                    TransactionalEmailOutbox.objects
                    .select_for_update(skip_locked=True)
                    .filter(status="pending", next_attempt_at__lte=timezone.now())
                    .order_by("created_at")
                    .first()
                )
                if not item:
                    break
                item.status = "processing"
                item.attempt_count += 1
                item.save(update_fields=["status", "attempt_count"])

            if not _otp_delivery_is_current(item, timezone.now()):
                item.status = "dead_letter"
                item.last_error_code = "OTP_EXPIRED_BEFORE_DELIVERY"
                item.save(update_fields=["status", "last_error_code"])
                results["failed"] += 1
                continue

            result = send_outbox_message(item)
            if result == "disabled":
                item.status = "pending"
                item.next_attempt_at = timezone.now() + timedelta(minutes=5)
                item.save(update_fields=["status", "next_attempt_at"])
                results["disabled"] += 1
                continue

            item.status = "sent"
            item.sent_at = timezone.now()
            item.last_error_code = ""
            item.save(update_fields=["status", "sent_at", "last_error_code"])
            results["sent"] += 1
        except Exception as exc:
            error_code = type(exc).__name__[:64]
            if item is not None:
                item.status = "dead_letter" if item.attempt_count >= 5 else "pending"
                item.last_error_code = error_code
                item.next_attempt_at = timezone.now() + timedelta(minutes=min(30, 2 ** min(item.attempt_count, 4)))
                item.save(update_fields=["status", "last_error_code", "next_attempt_at"])
                logger.warning(
                    "transactional_email_delivery_failed",
                    extra={"outbox_id": str(item.pk), "error_code": error_code, "attempt_count": item.attempt_count},
                )
            results["failed"] += 1
    return results
