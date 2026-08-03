import hashlib
import hmac
import json

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import NotificationEvent, WebhookDelivery


@shared_task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def deliver_webhook(self, delivery_id):
    delivery = WebhookDelivery.objects.select_related("subscription", "event").get(id=delivery_id)
    if not delivery.subscription.is_active:
        return
    event = delivery.event
    body = json.dumps({
        "id": str(event.id), "type": event.category, "title": event.title,
        "message": event.message, "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }, separators=(",", ":")).encode()
    signature = hmac.new(delivery.subscription.secret.encode(), body, hashlib.sha256).hexdigest()
    delivery.attempts += 1
    try:
        response = requests.post(
            delivery.subscription.url, data=body,
            headers={"Content-Type": "application/json", "X-Codestra-Event": event.category,
                     "X-Codestra-Signature-256": f"sha256={signature}"},
            timeout=getattr(settings, "WEBHOOK_TIMEOUT_SECONDS", 10), allow_redirects=False,
        )
        delivery.response_code = response.status_code
        response.raise_for_status()
        delivery.status = "S"
        delivery.delivered_at = timezone.now()
        delivery.last_error = ""
    except requests.RequestException as exc:
        delivery.status = "F"
        delivery.last_error = str(exc)[:500]
        delivery.save()
        raise
    delivery.save()


@shared_task
def purge_expired_notifications():
    cutoff = timezone.now() - timezone.timedelta(days=getattr(settings, "NOTIFICATION_RETENTION_DAYS", 90))
    deleted, _ = NotificationEvent.objects.filter(created_at__lt=cutoff).delete()
    return deleted
