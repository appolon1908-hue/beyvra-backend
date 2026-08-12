from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .services import notification_group, tenant_for


class PrivateNotificationConsumer(AsyncJsonWebsocketConsumer):
    """Read-only private notification stream; identity comes only from auth scope."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.notification_group = notification_group(tenant_for(user), user.pk)
        await self.channel_layer.group_add(self.notification_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group = getattr(self, "notification_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        await self.send_json(
            {
                "type": "error",
                "code": "READ_ONLY_STREAM",
                "message": "The requested action is not available.",
            }
        )

    async def notification_created(self, event):
        await self.send_json(
            {"type": "notification.created", "notification": event["notification"]}
        )
