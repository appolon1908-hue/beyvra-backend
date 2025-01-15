from .base import BaseConsumer
from channels.db import database_sync_to_async

class AdminConsumer(BaseConsumer):
    """
    Admin-only consumer for system-wide notifications
    and monitoring.
    """
    async def connect(self):
        await super().connect()
        
        if not await self.is_admin():
            await self.close()
            return
            
        await self.channel_layer.group_add("admin_notifications", self.channel_name)

    @database_sync_to_async
    def is_admin(self):
        return self.scope["user"].is_staff

    async def admin_alert(self, event):
        await self.send_json({
            'type': 'admin_alert',
            'data': event['data']
        })
