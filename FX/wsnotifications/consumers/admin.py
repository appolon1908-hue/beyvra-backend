from .base import BaseConsumer
import json
import logging
from wsnotifications.handlers import admin_handlers

logger = logging.getLogger(__name__)



class AdminDataConsumer(BaseConsumer):
    """
    Handles real-time trade data updates including prices,
    volumes, and other trade indicators.
    """
    
    async def connect(self):
        user = self.scope['user']
        await super().connect()
        if user.is_authenticated:
            if user.is_superuser:
                logger.info(user.role)
                await self.channel_layer.group_add("Admin", self.channel_name)
                logger.info("Connecting to group Admin")  
            else:
                super().disconnect()     
        else:
            super().disconnect()

    async def disconnect(self, close_code):
        user =self.scope['user']
        await self.channel_layer.group_discard("Admin", self.channel_name)
        await self.channel_layer.group_add("Admin", self.channel_name)
        await super().disconnect(close_code)

    async def send_message(self, event):
        await admin_handlers.dispatch_message(self, event)
