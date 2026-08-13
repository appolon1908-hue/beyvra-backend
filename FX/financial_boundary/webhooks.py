"""Future provider webhook verification with no provider or network access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
import hashlib
import hmac
import json
import re
import time
import uuid

from .eventing import FinancialEventEnvelope, canonical_payload, consume_financial_event


class WebhookDenied(PermissionError):
    code = "INVALID_WEBHOOK"


@dataclass(frozen=True)
class VerifiedProviderWebhook:
    provider_id: str
    provider_event_id: str
    envelope: FinancialEventEnvelope


def webhook_signature(*, provider_id: str, event_id: str, timestamp: int,
                      raw_body: bytes, secret: bytes) -> str:
    message = f"{timestamp}.{event_id}.{provider_id}.".encode("ascii") + raw_body
    return "v1=" + hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_provider_webhook(*, expected_provider_id: str, tenant_ref, headers: dict,
                            raw_body: bytes, secret: bytes, now=None,
                            replay_window_seconds: int = 300) -> VerifiedProviderWebhook:
    provider_id = headers.get("X-Provider-Id", "")
    event_id = headers.get("X-Event-Id", "")
    timestamp_text = headers.get("X-Timestamp", "")
    signature = headers.get("X-Signature", "")
    if not re.fullmatch(r"[a-z0-9_-]{2,32}", expected_provider_id) or provider_id != expected_provider_id:
        raise WebhookDenied("provider identity denied")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{6,128}", event_id):
        raise WebhookDenied("event identity denied")
    try:
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        raise WebhookDenied("timestamp denied") from None
    current = int(now if now is not None else time.time())
    if replay_window_seconds < 1 or abs(current - timestamp) > replay_window_seconds:
        raise WebhookDenied("timestamp outside replay window")
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise WebhookDenied("webhook authority unavailable")
    expected = webhook_signature(
        provider_id=provider_id, event_id=event_id, timestamp=timestamp,
        raw_body=raw_body, secret=secret,
    )
    if not hmac.compare_digest(expected, signature):
        raise WebhookDenied("signature denied")
    try:
        payload = json.loads(raw_body)
    except (TypeError, ValueError, UnicodeDecodeError):
        raise WebhookDenied("payload denied") from None
    payload, _ = canonical_payload(payload)
    event_type = payload.pop("event_type", None)
    if not isinstance(event_type, str):
        raise WebhookDenied("event type denied")
    event_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-provider:{provider_id}:{event_id}")
    occurred_at = datetime.fromtimestamp(timestamp, tz=datetime_timezone.utc)
    try:
        envelope = FinancialEventEnvelope(
            event_id=event_uuid, event_type=event_type, schema_version=1,
            occurred_at=occurred_at,
            correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-correlation:{provider_id}:{event_id}"),
            causation_id=None, tenant_ref=tenant_ref, payload=payload,
        )
    except (TypeError, ValueError) as exc:
        raise WebhookDenied("event contract denied") from exc
    return VerifiedProviderWebhook(provider_id, event_id, envelope)


def consume_verified_webhook(webhook: VerifiedProviderWebhook, handler) -> bool:
    return consume_financial_event(webhook.envelope, handler)
