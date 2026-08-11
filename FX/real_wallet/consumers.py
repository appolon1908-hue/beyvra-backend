from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .stream import StreamCursor, validate_resume


class RealWalletStreamConsumer(AsyncJsonWebsocketConsumer):
    """Authenticated private wallet stream with explicit resume semantics."""

    allowed_channels = {
        "account.security", "compliance.status", "wallet.balance", "wallet.deposit",
        "wallet.withdrawal", "wallet.transfer", "wallet.restriction", "notification",
    }

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close(code=4401)
            return
        self.subscriptions = set()
        await self.accept()
        await self.send_json({"type": "stream.ready", "version": "1", "resume_supported": True})

    async def disconnect(self, close_code):
        for channel in getattr(self, "subscriptions", set()):
            await self.channel_layer.group_discard(self._group_name(channel), self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})
        elif action == "subscribe":
            channels = content.get("channels", [])
            if not isinstance(channels, list) or any(channel not in self.allowed_channels for channel in channels):
                await self.send_json({"type": "error", "code": "UNSUPPORTED_CHANNEL"})
                return
            for channel in channels:
                await self.channel_layer.group_add(self._group_name(channel), self.channel_name)
                self.subscriptions.add(channel)
            await self.send_json({"type": "subscribed", "channels": sorted(self.subscriptions)})
        elif action == "unsubscribe":
            for channel in content.get("channels", []):
                if channel in self.subscriptions:
                    await self.channel_layer.group_discard(self._group_name(channel), self.channel_name)
                    self.subscriptions.discard(channel)
            await self.send_json({"type": "unsubscribed", "channels": sorted(self.subscriptions)})
        elif action == "resume":
            sequence = content.get("sequence", 0)
            try:
                decision = validate_resume(StreamCursor(channel="", sequence=sequence), content.get("latest_sequence", sequence))
            except (TypeError, ValueError):
                await self.send_json({"type": "error", "code": "INVALID_RESUME_CURSOR"})
                return
            await self.send_json({"type": "resume.result", "decision": decision})
        else:
            await self.send_json({"type": "error", "code": "UNSUPPORTED_ACTION"})

    @staticmethod
    def _group_name(channel):
        return f"real-wallet-stream:{channel}"

    async def wallet_event(self, event):
        await self.send_json(event["payload"])
