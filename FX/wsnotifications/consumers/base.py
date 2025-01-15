from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
import aiohttp

class BaseConsumer(AsyncJsonWebsocketConsumer):
    """
    Base consumer class with common functionality.
    Handles auth, logging, and basic message routing.
    """
    async def connect(self):
        
        await self.accept()
        
    async def disconnect(self, close_code):
        self.keep_sending = False
        await self.session.close()

    async def receive(self, text_data):
        pass

    