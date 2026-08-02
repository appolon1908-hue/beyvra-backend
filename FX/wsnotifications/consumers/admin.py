from .base import BaseConsumer
import json



class AdminDataConsumer(BaseConsumer):
    """
    Handles real-time market data updates including prices,
    volumes, and other market indicators.
    """
    async def connect(self):
        await super().connect()
        user = self.scope["user"]
        if not user.is_authenticated:
            return
        if not user.is_staff:
            await self.close(code=4403)
            return
        await self.channel_layer.group_add("admin_notification", self.channel_name)

    async def disconnect(self, close_code):
        user = self.scope["user"]
        if user.is_authenticated and user.is_staff:
            await self.channel_layer.group_discard("admin_notification", self.channel_name)
        await super().disconnect(close_code)

    async def send_price_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "price_update",
            "data": message
        }))
