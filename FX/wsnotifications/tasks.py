import logging
from celery import shared_task, group
import requests
from asgiref.sync import async_to_sync
from .service import UserNotificationService
from django.core.cache import cache
from wsnotifications.models import AssetSubscription


logger = logging.getLogger(__name__)


@shared_task(name='wsnotifications.tasks.periodic_price_updates')
def periodic_price_updates():
    url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd'
    UserNotificationService.market_price_update(url)



@shared_task(name='wsnotifications.tasks.send_email_verification_reminder')
def send_email_verification_reminder():
    UserNotificationService.send_email_verification_message()
    
    
@shared_task(name='wsnotifications.tasks.send_price_threshold_update')
def send_price_threshold_update():
    UserNotificationService.send_price_threshold_update()

@shared_task(name='wsnotifications.tasks.send_asset_specific_updates')
def send_asset_specific_updates():
    """Fetch and broadcast price updates for all subscribed assets"""
    try:
        # Get unique subscribed assets
        subscribed_assets = AssetSubscription.objects.values_list(
            'asset_id', flat=True
        ).distinct()
        
        if not subscribed_assets:
            return
        
        # Generate URL for fetching prices
        assets_query = ','.join(subscribed_assets)
        logger.info(assets_query)
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={assets_query}&vs_currencies=usd"
        
        response = UserNotificationService.make_request(url)
        if response.status_code == 200:
            data = response.json()
            
            # Send updates for each asset
            for asset_id, price_info in data.items():
                UserNotificationService.sync_send_asset_price_update(
                    asset_id,
                    price_info['usd']
                )
                
    except Exception as e:
        logger.error(f"Error updating asset prices: {e}")
        raise

    
    
