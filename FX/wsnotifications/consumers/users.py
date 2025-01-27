from .base import BaseConsumer
import json
from wsnotifications.handlers import user_handlers
from wsnotifications.service import UserNotificationService


import logging

logger = logging.getLogger(__name__)


class UserConsumer(BaseConsumer):
    """
    Handles real-time trade data updates including prices,
    volumes, and other trade indicators.
    """
    
    async def connect(self):
        await super().connect()
        user = self.scope['user']
        if user.is_authenticated:
            group_name = f"user_{user.id}"
            logger.info(group_name)
            await self.channel_layer.group_add(group_name, self.channel_name)
            logger.info("Connecting to group users")
            await self.channel_layer.group_add("users", self.channel_name)    
            logger.info("Connected to group Users")    
        else:
            pass

    async def disconnect(self, close_code):
        user =self.scope['user']
        await self.channel_layer.group_discard(f"user_{user.id}", self.channel_name)
        await self.channel_layer.group_add(f"users", self.channel_name)
        await super().disconnect(close_code)

    async def send_message(self, event):
        await user_handlers.dispatch_message(self, event)
        
        
        
class PriceThresholdConsumer(BaseConsumer):
    """
    Handles real-time trade data updates including prices,
    volumes, and other trade indicators.
    """
    
    async def connect(self):
        await super().connect()
        user = self.scope['user']
        if user.is_authenticated:
            group_name = f"pricethreshold_{user.id}"
            logger.info("Price Threshold Added")
            await self.channel_layer.group_add(group_name, self.channel_name)   
        else:
            await super().disconnect()


    async def disconnect(self, close_code):
        user =self.scope['user']
        await self.channel_layer.group_discard(f"user_{user.id}", self.channel_name)
        await self.channel_layer.group_add(f"users", self.channel_name)
        await super().disconnect(close_code)

    async def send_message(self, event):
        await user_handlers.dispatch_message(self, event)



