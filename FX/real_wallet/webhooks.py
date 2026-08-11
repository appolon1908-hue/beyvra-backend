import hashlib
import hmac
import ipaddress
import secrets
import socket
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import WebhookEvent, WebhookSecretVersion


class WebhookSecurityError(ValueError):
    pass


def _master_key() -> bytes:
    path = getattr(settings, "REAL_WALLET_WEBHOOK_MASTER_KEY_FILE", "")
    if not path:
        raise WebhookSecurityError("webhook encryption key is not configured")
    with open(path, "rb") as handle:
        key = handle.read()
    if len(key) != 32:
        raise WebhookSecurityError("webhook encryption key must be 32 bytes")
    return key


def encrypt_secret(secret: str) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return nonce, AESGCM(_master_key()).encrypt(nonce, secret.encode(), None)


def decrypt_secret(nonce: bytes, ciphertext: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(_master_key()).decrypt(nonce, ciphertext, None).decode()


def secret_fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def validate_webhook_destination(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise WebhookSecurityError("webhook destination must be HTTPS without embedded credentials")
    if parsed.port not in (None, 443):
        raise WebhookSecurityError("webhook destination port is not allowed")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname or hostname in {"localhost", "localhost.localdomain"}:
        raise WebhookSecurityError("webhook destination is not allowed")
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise WebhookSecurityError("webhook destination cannot be resolved") from exc
    for address in addresses:
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified:
            raise WebhookSecurityError("webhook destination resolves to a restricted address")


def signature_headers(*, timestamp: int, webhook_id: str, raw_body: bytes, secret: str, key_id: str) -> dict[str, str]:
    signed = f"{timestamp}.{webhook_id}.".encode() + raw_body
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {
        "Webhook-Id": webhook_id,
        "Webhook-Timestamp": str(timestamp),
        "Webhook-Key-Id": key_id,
        "Webhook-Signature": f"v1={signature}",
        "Content-Type": "application/json",
    }


def verify_signature(*, timestamp: int, webhook_id: str, raw_body: bytes, signature: str, secret: str, ttl_seconds: int = 300) -> bool:
    if abs(int(datetime.now(dt_timezone.utc).timestamp()) - timestamp) > ttl_seconds:
        return False
    expected = signature_headers(timestamp=timestamp, webhook_id=webhook_id, raw_body=raw_body, secret=secret, key_id="verify")["Webhook-Signature"]
    return hmac.compare_digest(expected, signature)


@transaction.atomic
def persist_inbound_event(*, tenant, event_id, event_type, payload, occurred_at):
    event, created = WebhookEvent.objects.get_or_create(
        tenant=tenant, event_id=event_id,
        defaults={"event_type": event_type, "payload": payload, "occurred_at": occurred_at},
    )
    return event, created


def create_secret_version(*, subscription, secret, key_id, key_version=1, expires_at=None):
    nonce, ciphertext = encrypt_secret(secret)
    return WebhookSecretVersion.objects.create(
        subscription=subscription, key_id=key_id, ciphertext=ciphertext, nonce=nonce,
        key_version=key_version, activated_at=timezone.now(), expires_at=expires_at,
        fingerprint=secret_fingerprint(secret),
    )
