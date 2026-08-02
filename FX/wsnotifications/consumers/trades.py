from .base import BaseConsumer
import json

class TradeConsumer(BaseConsumer):
    """
    Handles real-time trade data updates including prices,
    volumes, and other trade indicators.
    """
    
    async def connect(self):
        await super().connect()
        user = self.scope['user']
        if user.is_authenticated:
             if user.is_staff:
                 await self.channel_layer.group_add('admin_notification', self.channel_name)
             await self.channel_layer.group_add(f"trades_updates{user.id}", self.channel_name)

    async def disconnect(self, close_code):
        user =self.scope['user']
        if not user.is_authenticated:
            return
        if user.is_staff:
            await self.channel_layer.group_discard("admin_notification", self.channel_name)
        await self.channel_layer.group_discard(f"trades_updates{user.id}", self.channel_name)
        await super().disconnect(close_code)

    async def send_price_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "price_update",
            "data": message
        }))


