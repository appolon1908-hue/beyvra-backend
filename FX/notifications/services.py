import logging
from django.utils import timezone
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import NotificationEvent, Notifications, UserNotifications, WebhookDelivery, WebhookSubscription
from integrations.crypto import encrypt_secret, fingerprint
from integrations.permissions import organization_for_user

logger = logging.getLogger(__name__)


def normalize_category(value):
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "GENERAL").upper()).strip("_") or "GENERAL"


def preference_enabled(user_id, category):
    """Missing preferences opt in; an explicit disabled preference opts out."""
    normalized = normalize_category(category)
    organization = organization_for_user(user_id)
    preferences = UserNotifications.objects.filter(user_id=user_id, organization=organization).select_related("notification")
    category_preference = next(
        (item for item in preferences if normalize_category(item.notification.name) == normalized), None
    )
    if category_preference is not None:
        return category_preference.is_enabled
    app_preference = next(
        (item for item in preferences if normalize_category(item.notification.name) in {"PUSH_NOTIFICATIONS", "APP_ALERTS"}),
        None,
    )
    return app_preference is None or app_preference.is_enabled


def emit_notification(*, user_id, title, message, category="GENERAL", payload=None, force=False):
    """Persist once, broadcast the same event, and queue matching webhooks."""
    if not user_id or (not force and not preference_enabled(user_id, category)):
        return None

    normalized = normalize_category(category)
    organization = organization_for_user(user_id)
    event = NotificationEvent.objects.create(
        user_id=user_id,
        organization=organization,
        title=str(title),
        message=str(message),
        category=normalized,
        payload=payload or {},
    )
    wire_event = {
        "id": str(event.id), "title": event.title, "message": event.message,
        "category": event.category, "payload": event.payload,
        "is_read": False, "created_at": event.created_at.isoformat(),
    }
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                f"user_{organization.id if organization else 'default'}_{user_id}", {"type": "send_message", "message": wire_event}
            )
        except Exception:
            logger.exception("Unable to broadcast notification %s", event.id)

    subscriptions = WebhookSubscription.objects.filter(user_id=user_id, organization=organization, is_active=True)
    for subscription in subscriptions:
        allowed = [normalize_category(item) for item in subscription.categories]
        if not allowed or normalized in allowed:
            delivery = WebhookDelivery.objects.create(subscription=subscription, event=event)
            transaction.on_commit(lambda delivery_id=delivery.id: _queue_webhook(delivery_id))
    return event


def _queue_webhook(delivery_id):
    try:
        from .tasks import deliver_webhook
        deliver_webhook.delay(str(delivery_id))
    except Exception:
        logger.exception("Unable to queue webhook delivery %s", delivery_id)


def encrypted_webhook_fields(secret):
    ciphertext, nonce, version = encrypt_secret(secret)
    return {"secret": None, "secret_ciphertext": ciphertext, "secret_nonce": nonce,
            "secret_key_version": version, "secret_fingerprint": fingerprint(secret),
            "secret_created_at": timezone.now()}
