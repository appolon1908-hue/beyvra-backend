from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User

from django.core.cache import cache
from wsnotifications.utils import db_online_users_count, db_user_connected, db_user_disconnected, can_access_group


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """
    Base consumer class with common functionality.
    Handles auth, logging, and basic message routing.
    """

    async def connect(self):
        await self.accept()
        user = self.scope['user']
        updated_user = await db_user_connected(user)
        print(updated_user)
        result = await db_online_users_count()
        ##result of active users will be sent to admin
        print(result)
        
        
    async def disconnect(self, close_code):
        user = self.scope['user']
        print(user)
        await db_user_disconnected(user)
        result =  await db_online_users_count(user)
        print(result)
        await self.close()

    async def receive(self, text_data):
        pass
