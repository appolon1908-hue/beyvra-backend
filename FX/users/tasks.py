import smtplib

from celery import shared_task
from users.models import PhoneVerificationCode, User, UserDeviceInfo

from .utils import (
    send_email_verification_email,
    send_mobile_verification_code,
    send_password_reset_link_email,
    send_user_device_info_alert,
    send_welcome_email,
    send_user_ban_email,
)


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
