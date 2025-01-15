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
        # await self.send_data()

    async def disconnect(self, close_code):
        self.keep_sending = False
        await self.session.close()

    async def receive(self, text_data):
        pass

    # async def send_data(self):
    #     """ Méthode à surcharger dans les sous-classes pour envoyer des données spécifiques. """
    #     pass

    
    # async def connect(self):
    #     if not self.scope["user"].is_authenticated:
    #         await self.close()
    #         return
            
    #     await self.accept()
    #     self.user_id = self.scope["user"].id
    #     print("Connected")
    #     # self.logger.info(f"WebSocket connected: {self.user_id}")

    # async def disconnect(self, close_code):
    #     # Leave all groups and cleanup
    #     print("Disconnected")
    #     # self.logger.info(f"WebSocket disconnected: {self.user_id}")
    #     await super().disconnect(close_code)

    # @database_sync_to_async
    # def get_user(self):
    #     return User.objects.get(id=self.user_id)