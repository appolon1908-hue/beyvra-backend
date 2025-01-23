from .base import BaseConsumer
import json
from django.core.cache import cache
from urllib.parse import parse_qs


import logging

logger = logging.getLogger(__name__)


class MarketDataConsumer(BaseConsumer):
    """
    Handles real-time market data updates including prices,
    volumes, and other market indicators.
    """

    async def connect(self):
        await super().connect()
        user = self.scope.get('user')
        logger.info(f"New {user}")
        query_string = self.scope["query_string"].decode("utf-8")
        query_params = dict(parse_qs(query_string))
        asset_id = query_params.get("asset_id")[0]
        logger.info(asset_id)

        if user and user.is_authenticated:
            if user.is_staff:
                await self.channel_layer.group_add(
                    'admin_notification',
                    self.channel_name
                )
            if asset_id:
                logger.info(True)
                asset_group_name = f'asset_{asset_id}'
                await self.channel_layer.group_add(
                    asset_group_name,
                    self.channel_name
                )
                
                cache.set('asset_id', asset_id, timeout=600)
            
            else:
                await self.channel_layer.group_add(
                    'market_prices',
                    self.channel_name
                )
        

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
        
    async def send_asset_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "send_asset_update",
            "data": message
        }))



