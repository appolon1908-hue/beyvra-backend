from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User

from django.core.cache import cache
from wsnotifications.utils import db_online_users_count, db_user_connected, db_user_disconnected


import logging

logger = logging.getLogger(__name__)


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """
    Base consumer class with common functionality.
    Handles auth, logging, and basic message routing.
    """

    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        logger.info(f"Base Consumer {user}")
        await db_user_connected(user)
        await db_online_users_count()
        
        
        
    async def disconnect(self, close_code):
        user = self.scope['user']
        if not user.is_authenticated:
            return
        await db_user_disconnected(user)
        await db_online_users_count()

    async def receive(self, text_data):
        pass
