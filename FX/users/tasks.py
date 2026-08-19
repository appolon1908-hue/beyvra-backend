from datetime import timedelta

from celery import shared_task
from users.models import PhoneVerificationCode, TransactionalEmailOutbox, User, UserDeviceInfo

from .utils import (
    send_email_verification_email,
    send_mobile_verification_code,
    send_password_reset_link_email,
    send_user_device_info_alert,
    send_welcome_email,
    send_user_ban_email,
)
from .email_verification import send_outbox_message
from notifications.email_client import EmailMiddlewareError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_transactional_email_outbox(self):
    item = None
    try:
        with transaction.atomic():
            now = timezone.now()
            item = TransactionalEmailOutbox.objects.select_for_update(skip_locked=True).filter(
                Q(status="pending", next_attempt_at__lte=now) | Q(status="processing", lease_expires_at__lt=now)
            ).order_by("next_attempt_at").first()
            if not item:
                return "empty"
            item.status = "processing"
            item.lease_expires_at = now + timedelta(minutes=2)
            item.attempt_count += 1
            item.save(update_fields=["status", "lease_expires_at", "attempt_count"])
        result = send_outbox_message(item)
        if result == "disabled":
            item.status = "pending"
            item.lease_expires_at = None
            item.next_attempt_at = timezone.now() + timedelta(minutes=5)
            item.save(update_fields=["status", "lease_expires_at", "next_attempt_at"])
            return result
        item.status = "sent"
        item.sent_at = timezone.now()
        item.provider_message_id = str(result.get("provider_message_id") or result.get("notification_id") or "")
        item.provider_status = str(result.get("status") or "QUEUED")
        item.lease_expires_at = None
        item.last_error_code = ""
        item.save(update_fields=["status", "sent_at", "provider_message_id", "provider_status", "lease_expires_at", "last_error_code"])
        return "sent"
    except EmailMiddlewareError as exc:
        if item is not None:
            item.status = "dead_letter" if not exc.retryable or item.attempt_count >= 5 else "pending"
            item.last_error_code = exc.error_class[:64]
            item.lease_expires_at = None
            delays = (1, 2, 10, 60, 240)
            item.next_attempt_at = timezone.now() + timedelta(minutes=delays[min(item.attempt_count - 1, 4)])
            item.save(update_fields=["status", "last_error_code", "lease_expires_at", "next_attempt_at"])
        return "failed"
    except Exception as exc:
        if item is not None:
            item.status = "dead_letter" if item.attempt_count >= 5 else "pending"
            item.last_error_code = type(exc).__name__[:64]
            item.lease_expires_at = None
            item.next_attempt_at = timezone.now() + timedelta(minutes=10)
            item.save(update_fields=["status", "last_error_code", "lease_expires_at", "next_attempt_at"])
        return "failed"
