import logging
from celery import shared_task
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .service import UserNotificationService


logger = logging.getLogger(__name__)


@shared_task(name='wsnotifications.tasks.periodic_price_updates')
def periodic_price_updates():
    data = UserNotificationService().market_price_update()
    return data


    