import hashlib
import hmac
import json
import time
from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from financial_boundary.webhooks import WebhookDenied, verify_provider_webhook

# In-memory durable inbox cache for duplicate suppression
WEBHOOK_INBOX_DEDUPLICATION = set()


class CanonicalProviderWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, provider):
        # 1. Allowlist verification
        allowed_providers = {"alpaca", "drivewealth", "polygon", "coinbase", "simulated"}
        if provider not in allowed_providers:
            return Response({"error": {"code": "PROVIDER_DISALLOWED"}}, status=403)

        # 2. Body size limit (1MB max)
        if len(request.body) > 1024 * 1024:
            return Response({"error": {"code": "PAYLOAD_TOO_LARGE"}}, status=413)

        # 3. Signature and replay check
        secret = getattr(settings, "PROVIDER_WEBHOOK_SECRET", b"default_super_secret_signing_key_32bytes_minimum!")
        if isinstance(secret, str):
            secret = secret.encode("utf-8")

        headers = {
            "X-Provider-Id": request.headers.get("X-Provider-Id", provider),
            "X-Event-Id": request.headers.get("X-Event-Id", ""),
            "X-Timestamp": request.headers.get("X-Timestamp", "0"),
            "X-Signature": request.headers.get("X-Signature", ""),
        }

        try:
            verified = verify_provider_webhook(
                expected_provider_id=provider,
                tenant_ref="default",
                headers=headers,
                raw_body=request.body,
                secret=secret,
                replay_window_seconds=300
            )
        except WebhookDenied as exc:
            return Response({"error": {"code": "INVALID_WEBHOOK", "message": str(exc)}}, status=401)

        # 4. Deduplication
        dedup_key = f"{provider}:{verified.provider_event_id}"
        if dedup_key in WEBHOOK_INBOX_DEDUPLICATION:
            return Response({"status": "duplicate"}, status=200)

        WEBHOOK_INBOX_DEDUPLICATION.add(dedup_key)
        return Response({"status": "accepted", "event_id": str(verified.envelope.event_id)}, status=202)
