from .base import BaseConsumer
import json




# User = get_user_model()

class MarketDataConsumer(BaseConsumer):
    """
    Handles real-time market data updates including prices,
    volumes, and other market indicators.
    """
    async def connect(self):
        await super().connect()
        await self.channel_layer.group_add("market_prices", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("market_prices", self.channel_name)
        await super().disconnect(close_code)

    async def send_price_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "price_update",
            "data": message
        }))

    # async def send_data(self):
       

    # async def send_market_snapshot(self):
    #     """Send initial market data snapshot"""
    #     # Get latest prices from your data source
    #     snapshot = await self.get_market_snapshot()
    #     await self.send_json({
    #         'type': 'market_snapshot',
    #         'data': snapshot
    #     })
