from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
import aiohttp
from asgiref.sync import sync_to_async
from django.core.cache import cache
from wsnotifications.utils import db_online_users_count, db_user_connected, db_user_disconnected




class BaseConsumer(AsyncJsonWebsocketConsumer):
    """
    Base consumer class with common functionality.
    Handles auth, logging, and basic message routing.
    """
    async def connect(self):
        user = self.scope['user']
        print(user)
        await self.accept()
        await db_user_connected(user)
        await db_online_users_count()
        
        
    async def disconnect(self, close_code):
        user = self.scope['user']
        print(user)
        await db_user_disconnected(user)
        result =  await db_online_users_count(user)
        print(result)
        await self.close()

    async def receive(self, text_data):
        pass

    # @sync_to_async
    # def add_connection(self, user_id):
    #     self.connected_users[user_id] = self.channel_name
    #     print(self.connected_users)
        
    # @sync_to_async
    # def remove_connection(self, user_id):
    #     # Remove user from cache or dictionary
    #     connections = cache.get('active_connections', {})
    #     connections.pop(user_id, None)
    #     cache.set('active_connections', connections, timeout=None)

    

# celery -A FX worker --loglevel=INFO --concurrency 1 -P solo
