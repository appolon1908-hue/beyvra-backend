import logging

from celery import shared_task
from django.utils import timezone
from middleware.log_activity import log
from security.models import AnomalyCheckSchedule, UserActivity, UserActivityActionTypes
from users.models import User, UserDeviceInfo

from .utils import send_user_anomaly_alert_to_admin


@shared_task
def async_send_user_anomaly_alert_to_admin(user_id, email_msg=None):
    user = User.objects.get(id=user_id)
    try:
        user_device_info = UserDeviceInfo.objects.get(user=user)
    except UserDeviceInfo.DoesNotExist as e:
        logging.warning(f"Error sending user anomaly alert to admin: {str(e)}")
        user_device_info = {}
    # capture anomaly into user activities
    log(
        request=None,
        action_type=UserActivityActionTypes.USER_ANOMALY_ALERT.value,
        desc=email_msg,
        err_msg=email_msg,
        user=user,
        user_device_info=user_device_info,
    )
    # mail to admin
    send_user_anomaly_alert_to_admin(user, user_device_info, email_msg)


@shared_task
def async_check_anomalies():
    schedule, created = AnomalyCheckSchedule.objects.get_or_create(defaults={"last_checked_time": timezone.now()})
    last_checked_time = schedule.last_checked_time
    new_anomalies = UserActivity.objects.filter(
        action_type=UserActivityActionTypes.USER_ANOMALY_ALERT.value, created_at__gt=last_checked_time
    )

    if new_anomalies.exists():
        logging.warning(new_anomalies)

        for anomaly in new_anomalies:
            try:
                user_device_info = UserDeviceInfo.objects.get(user=anomaly.user)
            except UserDeviceInfo.DoesNotExist:
                user_device_info = {}

            alert_message = (
                f"New user anomaly detected:\nUser: {anomaly.user} -> {anomaly.action_type} "
                f"Performed: {anomaly.description} at -> {anomaly.created_at} "
                f"from IP: {anomaly.ip_address}, {anomaly.geolocation}"
            )

            try:
                # mail to admin
                send_user_anomaly_alert_to_admin(anomaly.user, user_device_info, alert_message)
            except Exception as e:
                logging.warning(e)

        # Update last checked time
        AnomalyCheckSchedule.update_last_checked_time(timezone.now())
