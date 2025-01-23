from .base import BaseConsumer
import json

class MarketDataConsumer(BaseConsumer):
    """
    Handles real-time market data updates including prices,
    volumes, and other market indicators.
    """
    
    async def connect(self):
        await super().connect()
        user = self.scope['user']
        if user.is_authenticated:
             if user.is_staff:
                 await self.channel_layer.group_add('admin_notification', self.channel_name)
             await self.channel_layer.group_add('market_prices', self.channel_name)

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



