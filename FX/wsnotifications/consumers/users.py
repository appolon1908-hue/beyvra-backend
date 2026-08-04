from .base import BaseConsumer
import json
from wsnotifications.handlers import user_handlers
from wsnotifications.service import UserNotificationService
from channels.db import database_sync_to_async
from integrations.models import OrganizationMembership


@database_sync_to_async
def _default_tenant_id(user_id):
    membership = OrganizationMembership.objects.filter(user_id=user_id).order_by("id").values_list("organization_id", flat=True).first()
    return str(membership) if membership else "default"


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
            self.tenant_id = await _default_tenant_id(user.id)
            group_name = f"user_{self.tenant_id}_{user.id}"
            logger.info(group_name)
            await self.channel_layer.group_add(group_name, self.channel_name)
            logger.info("Connecting to group users")
            await self.channel_layer.group_add("users", self.channel_name)    
            logger.info("Connected to group Users")    
        else:
            pass

    async def disconnect(self, close_code):
        user =self.scope['user']
        if not user.is_authenticated:
            return
        await self.channel_layer.group_discard(f"user_{getattr(self, 'tenant_id', 'default')}_{user.id}", self.channel_name)
        await self.channel_layer.group_discard("users", self.channel_name)
        await super().disconnect(close_code)

    async def send_message(self, event):
        await user_handlers.dispatch_message(self, event)
