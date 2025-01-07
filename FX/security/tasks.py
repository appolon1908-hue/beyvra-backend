from celery import shared_task
from users.models import User, UserDeviceInfo
from .utils import send_user_anomaly_alert_to_admin

@shared_task
def async_send_user_anomaly_alert_to_admin(user_id, email_msg=None):
    user = User.objects.get(id=user_id)
    try:
        user_device_info = UserDeviceInfo.objects.get(user=user)
    except UserDeviceInfo.DoesNotExist:
        print("Error sending user anomaly alert to admin: ", str(e))
        user_device_info={}
    send_user_anomaly_alert_to_admin(user, user_device_info, email_msg)
