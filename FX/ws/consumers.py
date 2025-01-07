# import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from .handlers import received_msg_handler
from .utils import on_connect, on_disconnect


class WebsocketConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # get user from the scope using the auth middleware
        # if user is not authenticated close connection
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close(401)
            return
        await self.accept()
        await on_connect(self, user)
        # join private user channel for updates
        private_group = str(user.id)
        await self.channel_layer.group_add(private_group, self.channel_name)
        self.groups.append(private_group)

    async def disconnect(self, close_code):
        user = self.scope["user"]
        if user.is_anonymous:
            return
        await on_disconnect(self, user)
        # leave from groups to save resources
        for group in self.groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        self.groups = []

    async def receive(self, text_data):
        data = json.loads(text_data)
        await received_msg_handler(self, data)

    async def send_message(self, data):
        await self.send(text_data=json.dumps(data))
