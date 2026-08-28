import hashlib
import os
import uuid
from datetime import datetime, timezone as datetime_timezone

from django.db import IntegrityError, transaction
from django.utils import timezone
from provider_governance.models import GovernanceStatus, ProviderDefinition
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from financial_boundary.models import ProviderWebhookInbox
from financial_boundary.webhooks import WebhookDenied, verify_provider_webhook

MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


def _provider_secret(provider):
    key = f"PROVIDER_WEBHOOK_SECRET_{provider.upper().replace('-', '_')}"
    secret = os.getenv(key, "")
    return secret.encode("utf-8") if secret else None


def _tenant_ref(request):
    value = request.headers.get("X-Tenant-Ref", "")
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


def _signature_timestamp(headers):
    try:
        return datetime.fromtimestamp(int(headers["X-Timestamp"]), tz=datetime_timezone.utc)
    except (KeyError, TypeError, ValueError, OSError):
        return timezone.now()


class CanonicalProviderWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, provider):
        if len(request.body) > MAX_WEBHOOK_BODY_BYTES:
            return Response({"error": {"code": "PAYLOAD_TOO_LARGE"}}, status=413)

        provider_record = (
            ProviderDefinition.objects.filter(
                provider_id=provider,
                enabled=True,
                approvals__status=GovernanceStatus.APPROVED,
            )
            .distinct()
            .first()
        )
        if provider_record is None:
            return Response({"error": {"code": "PROVIDER_DISALLOWED"}}, status=403)

        tenant_ref = _tenant_ref(request)
        if tenant_ref is None:
            return Response({"error": {"code": "TENANT_REQUIRED"}}, status=400)

        secret = _provider_secret(provider)
        if secret is None:
            return Response({"error": {"code": "WEBHOOK_AUTHORITY_UNAVAILABLE"}}, status=503)

        headers = {
            "X-Provider-Id": request.headers.get("X-Provider-Id", provider),
            "X-Event-Id": request.headers.get("X-Event-Id", ""),
            "X-Timestamp": request.headers.get("X-Timestamp", ""),
            "X-Signature": request.headers.get("X-Signature", ""),
        }

        try:
            verified = verify_provider_webhook(
                expected_provider_id=provider,
                tenant_ref=tenant_ref,
                headers=headers,
                raw_body=request.body,
                secret=secret,
                replay_window_seconds=300,
            )
        except WebhookDenied as exc:
            return Response(
                {"error": {"code": "INVALID_WEBHOOK", "message": str(exc)}},
                status=401,
            )

        payload_hash = hashlib.sha256(request.body).hexdigest()
        payload_reference = f"sha256:{payload_hash}"
        request_id = request.headers.get("X-Request-Id", "")[:128]

        try:
            with transaction.atomic():
                inbox = ProviderWebhookInbox.objects.create(
                    provider=verified.provider_id,
                    external_event_id=verified.provider_event_id,
                    tenant_id=tenant_ref,
                    payload_hash=payload_hash,
                    encrypted_payload=request.body,
                    payload_reference=payload_reference,
                    signature_timestamp=_signature_timestamp(headers),
                    status=ProviderWebhookInbox.Status.PENDING,
                    next_attempt_at=timezone.now(),
                    request_id=request_id,
                )
        except IntegrityError:
            return Response({"status": "duplicate"}, status=200)

        return Response(
            {
                "status": "accepted",
                "event_id": str(verified.envelope.event_id),
                "inbox_id": str(inbox.id),
            },
            status=202,
        )
