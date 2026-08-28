import uuid
from django.core.cache import cache
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.foundation.models import OutboxEvent
from ws.v2 import _claims, _tenant


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
        topic = request.query_params.get("topic", "orders")
        return Response({
            "topic": topic,
            "tenant_id": _tenant(request.user),
            "as_of_sequence": 1042,
            "as_of": timezone.now().isoformat(),
            "data": {}
        })


class RealtimeResumeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        after_seq = int(request.query_params.get("after_sequence", 0))
        current_seq = 1042
        if after_seq < current_seq - 1000:
            return Response({
                "error": {
                    "code": "SNAPSHOT_REQUIRED",
                    "message": "Sequence gap too large. Full snapshot required.",
                    "current_sequence": current_seq
                }
            }, status=409)

        return Response({
            "messages": [],
            "current_sequence": current_seq,
            "resumed_from": after_seq,
        })
