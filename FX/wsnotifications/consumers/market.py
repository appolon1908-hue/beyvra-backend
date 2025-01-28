from .base import BaseConsumer
import json
from django.core.cache import cache
from channels.db import database_sync_to_async
from urllib.parse import parse_qs
from wsnotifications.utils import subscribe_to_asset, unsubscribe_from_asset
from wsnotifications.models import AssetSubscription


import logging

logger = logging.getLogger(__name__)


class MarketDataConsumer(BaseConsumer):
    """
    Handles real-time market data updates including prices,
    volumes, and other market indicators.
    """

    async def connect(self):
        await super().connect()
        self.user = self.scope.get('user')
        logger.info(self.user)
        if self.user and self.user.is_authenticated:
            subscriptions = await self.get_user_subscriptions()
            logger.info(subscriptions)
            if subscriptions:
                for subscription in subscriptions:
                    group_name = f"price_updates_{subscription.asset_id}"
                    await self.channel_layer.group_add(
                        group_name,
                        self.channel_name
                    )
            else:
                await self.channel_layer.group_add(
                'market_prices',
                self.channel_name
              )
        else:
            await super().disconnect()
            

    async def disconnect(self, close_code):
        user =self.scope['user']
        if user.is_staff:
            await self.channel_layer.group_discard("market_prices", self.channel_name)
        await self.channel_layer.group_discard("admin_notifications", self.channel_name)
        await super().disconnect(close_code)
        

    async def send_price_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "price_update",
            "data": message
        }))
        
    async def price_update(self, event):
        """Handle incoming price updates"""
        await self.send(text_data=json.dumps(event['message']))
        
    @database_sync_to_async
    def get_user_subscriptions(self):
        return list(AssetSubscription.objects.filter(user=self.user))
    
    @database_sync_to_async
    def subscribe_to_asset(self, asset_id):
        AssetSubscription.objects.get_or_create(
            user=self.user,
            asset_id=asset_id
        )
        return asset_id
    
    @database_sync_to_async
    def unsubscribe_from_asset(self, asset_id):
        AssetSubscription.objects.filter(
            user=self.user,
            asset_id=asset_id
        ).delete()
        return asset_id
        
    async def receive(self, text_data):
        """Handle subscription/unsubscription requests"""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            asset_id = data.get('asset_id')
            
            if action == 'subscribe':
                await self.subscribe_to_asset(asset_id)
            elif action == 'unsubscribe':
                await self.unsubscribe_from_asset(asset_id)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))



