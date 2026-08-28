import uuid
from django.core.cache import cache
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from ws.recovery import SnapshotRequired, resume, snapshot
from ws.v2 import _channel_entry, _tenant

LEGACY_TOPIC_CHANNELS = {
    "orders": "demo.order",
    "executions": "demo.execution",
    "positions": "demo.position",
    "notifications": "notification",
    "market-status": "market.status",
}


def _requested_channel(request):
    raw = request.query_params.get("channel") or request.query_params.get("topic") or "orders"
    return LEGACY_TOPIC_CHANNELS.get(raw, raw)


class RealtimeTicketView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ticket_id = str(uuid.uuid4())
        tenant_id = _tenant(request.user)
        cache.set(
            ticket_id,
            {"user_id": request.user.pk, "tenant_id": tenant_id},
            timeout=60,
        )
        return Response({
            "ticket": ticket_id,
            "tenant_id": tenant_id,
            "user_id": str(request.user.pk),
            "expires_in_seconds": 60,
            "created_at": timezone.now().isoformat(),
        }, status=201)


class RealtimeSnapshotView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        channel = _requested_channel(request)
        if not _channel_entry(channel)[1]:
            return Response({"error": {"code": "UNSUPPORTED_CHANNEL"}}, status=400)
        return Response(snapshot(tenant_ref=_tenant(request.user), channel=channel))


class RealtimeResumeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        channel = _requested_channel(request)
        if not _channel_entry(channel)[1]:
            return Response({"error": {"code": "UNSUPPORTED_CHANNEL"}}, status=400)
        try:
            after_seq = int(request.query_params.get("after_sequence", 0))
        except (TypeError, ValueError):
            return Response({"error": {"code": "INVALID_CURSOR"}}, status=400)
        if after_seq < 0:
            return Response({"error": {"code": "INVALID_CURSOR"}}, status=400)
        try:
            return Response(resume(tenant_ref=_tenant(request.user), channel=channel, after_sequence=after_seq))
        except SnapshotRequired as exc:
            return Response({
                "error": {
                    "code": "SNAPSHOT_REQUIRED",
                    "message": "Sequence gap too large. Full snapshot required.",
                    "current_sequence": exc.current_sequence,
                }
            }, status=409)
