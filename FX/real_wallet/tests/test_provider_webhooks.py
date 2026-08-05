from unittest.mock import patch

from django.test import TestCase

from integrations.models import Organization, OrganizationMembership
from real_wallet.models import ProviderConnection
from real_wallet.provider_webhooks import (
    ProviderWebhookRejected,
    mark_provider_webhook_processed,
    receive_provider_webhook,
)
from users.models import User


class ProviderWebhookReceiptTests(TestCase):
    def test_verified_receipt_is_deduplicated_and_processed(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            user = User.objects.create(email="provider@example.com", phone_number="+12025550003")
        tenant = Organization.objects.create(name="Provider tenant")
        OrganizationMembership.objects.create(user=user, organization=tenant)
        connection = ProviderConnection.objects.create(
            tenant=tenant, provider="sandbox", connection_type="custody", encrypted_config=b"sandbox", status="DISABLED"
        )
        receipt, created = receive_provider_webhook(
            connection=connection, provider_event_id="provider-event-1", event_type="transaction.completed",
            payload={"synthetic": True}, signature_verified=True,
        )
        replay, replay_created = receive_provider_webhook(
            connection=connection, provider_event_id="provider-event-1", event_type="transaction.completed",
            payload={"synthetic": True}, signature_verified=True,
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(receipt.id, replay.id)
        self.assertEqual(mark_provider_webhook_processed(receipt.id).status, "PROCESSED")

    def test_invalid_signature_is_rejected_before_persistence(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            user = User.objects.create(email="provider-invalid@example.com", phone_number="+12025550004")
        tenant = Organization.objects.create(name="Invalid provider tenant")
        connection = ProviderConnection.objects.create(
            tenant=tenant, provider="sandbox", connection_type="custody", encrypted_config=b"sandbox", status="DISABLED"
        )
        with self.assertRaises(ProviderWebhookRejected):
            receive_provider_webhook(
                connection=connection, provider_event_id="bad", event_type="x", payload={}, signature_verified=False,
            )
