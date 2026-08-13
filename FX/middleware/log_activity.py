import logging

from django.db import transaction
from security.models import UserActivity, UserActivityActionStatus, UserActivityActionTypes
from users.models import UserDeviceInfo
from users.utils import get_ip_address, get_user_agent, get_user_location_mod

logger = logging.getLogger(__name__)


def log(
    request,
    action_type: UserActivityActionTypes,
    desc: str,
    err_msg: str,
    status_code=200,
    accepted_status_code: tuple[int, any] = (200, 201, 302, 301),
    user=None,
    user_device_info: UserDeviceInfo = None,
):
    try:
        # Gather request metadata
        user_agent = get_user_agent(request) if request else user_device_info.user_agent
        ip_address = get_ip_address(request) if request else user_device_info.ip_address
        user_location = get_user_location_mod(ip_address) if request else user_device_info.location
        device_type = user_agent["device_type"] if request else user_device_info.device
        device_model = user_agent["device_model"] if request else user_device_info.device

        # Using transaction to ensure data integrity
        data = {
            "user": user,
            "anonymous_user": "" if user else "Unknown User",
            "action_type": action_type,
            "action_status": (
                UserActivityActionStatus.SUCCESS.value
                if status_code in accepted_status_code
                else UserActivityActionStatus.FAILED.value
            ),
            "description": (desc if status_code in accepted_status_code else err_msg),
            "ip_address": ip_address,
            "geolocation": user_location,
            "device_type": device_type,
            "device_model": device_model,
            "user_agent": user_agent["user_agent"] if request else user_device_info.user_agent,
        }
        with transaction.atomic():
            UserActivity.objects.create(**data)
    except Exception as e:
        logger.warning("Error logging user update activity in middleware")
