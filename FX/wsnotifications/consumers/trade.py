from .base import BaseConsumer

class TradeConsumer(BaseConsumer):
    """
    Handles trade execution updates and confirmations.
    Manages user-specific trade groups.
    """
    async def connect(self):
        await super().connect()
        self.user_group = f"trades_user_{self.user_id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.user_group, self.channel_name)
        await super().disconnect(close_code)

    async def trade_update(self, event):
        await self.send_json({
            'type': 'trade_update',
            'data': event['data']
        })
