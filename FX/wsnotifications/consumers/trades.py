from .base import BaseConsumer
import json
from channels.db import database_sync_to_async
from integrations.models import OrganizationMembership


@database_sync_to_async
def _default_tenant_id(user_id):
    membership = OrganizationMembership.objects.filter(user_id=user_id).order_by("id").values_list("organization_id", flat=True).first()
    return str(membership) if membership else "default"

class TradeConsumer(BaseConsumer):
    """
    Handles real-time trade data updates including prices,
    volumes, and other trade indicators.
    """
    
    async def connect(self):
        await super().connect()
        user = self.scope['user']
        if user.is_authenticated:
             self.tenant_id = await _default_tenant_id(user.id)
             if user.is_staff:
                 await self.channel_layer.group_add('admin_notification', self.channel_name)
             await self.channel_layer.group_add(f"trades_updates_{self.tenant_id}_{user.id}", self.channel_name)

    async def disconnect(self, close_code):
        user =self.scope['user']
        if not user.is_authenticated:
            return
        if user.is_staff:
            await self.channel_layer.group_discard("admin_notification", self.channel_name)
        await self.channel_layer.group_discard(f"trades_updates_{getattr(self, 'tenant_id', 'default')}_{user.id}", self.channel_name)
        await super().disconnect(close_code)

    async def send_price_update(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({
            "type": "price_update",
            "data": message
        }))
