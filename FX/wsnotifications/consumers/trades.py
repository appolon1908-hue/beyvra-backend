from .base import BaseConsumer
import json
from channels.db import database_sync_to_async
from integrations.models import OrganizationMembership
from urllib.parse import parse_qs


@database_sync_to_async
def _tenant_id_for_user(user_id, requested=None):
    memberships = OrganizationMembership.objects.filter(user_id=user_id)
    if requested and memberships.filter(organization_id=requested).exists():
        return str(requested)
    membership = memberships.order_by("id").values_list("organization_id", flat=True).first()
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
             query = parse_qs(self.scope.get("query_string", b"").decode())
             requested_tenant = query.get("organization_id", [None])[0]
             self.tenant_id = await _tenant_id_for_user(user.id, requested_tenant)
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
