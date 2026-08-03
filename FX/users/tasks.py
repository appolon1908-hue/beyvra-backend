import smtplib
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
from django.db import transaction
from django.utils import timezone


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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_transactional_email_outbox(self):
    item = None
    try:
        with transaction.atomic():
            item = TransactionalEmailOutbox.objects.select_for_update(skip_locked=True).filter(status="pending", next_attempt_at__lte=timezone.now()).first()
            if not item:
                return "empty"
            item.status = "processing"
            item.attempt_count += 1
            item.save(update_fields=["status", "attempt_count"])
        result = send_outbox_message(item)
        if result == "disabled":
            item.status = "pending"
            item.next_attempt_at = timezone.now() + timedelta(minutes=5)
            item.save(update_fields=["status", "next_attempt_at"])
            return result
        item.status = "sent"
        item.sent_at = timezone.now()
        item.last_error_code = ""
        item.save(update_fields=["status", "sent_at", "last_error_code"])
        return "sent"
    except Exception as exc:
        if item is not None:
            item.status = "dead_letter" if item.attempt_count >= 3 else "pending"
            item.last_error_code = type(exc).__name__[:64]
            item.next_attempt_at = timezone.now() + timedelta(minutes=2)
            item.save(update_fields=["status", "last_error_code", "next_attempt_at"])
        return "failed"
