import logging
from celery import shared_task
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .service import UserNotificationService
from django.core.cache import cache


logger = logging.getLogger(__name__)


@shared_task(name='wsnotifications.tasks.periodic_price_updates')
def periodic_price_updates():
    url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd'
    return UserNotificationService.market_price_update(url)



@shared_task(name='wsnotifications.tasks.send_asset_specific_updates')
def send_asset_specific_updates():
    asset_id = cache.get('asset_id')
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={asset_id}&vs_currencies=usd"
    data = UserNotificationService.handle_asset_specific_sub(url, asset_id)
    cache.delete('asset_id')
    return data



@shared_task(name='wsnotifications.tasks.send_email_verification_reminder')
def send_email_verification_reminder():
    data = UserNotificationService.send_email_verification_message()
    return data

@shared_task(name='wsnotifications.tasks.send_price_threshold_update')
def send_price_threshold_update():
    asset_id = cache.get('asset_id')
    data = UserNotificationService.send_price_threshold_update()
    return data