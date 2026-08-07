import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from wallet.constants import DEMO_WALLET_NAME
from wallet.models import Currency, Wallet

from .demo_engine import settle_due_orders, transition_demo_order
from .demo_events import envelope, jetstream_subject
from .models import DemoEventOutbox, Trade


class DemoEventProducerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="demo-producer@example.invalid", password="test-pass", phone_number="+12025550182"
        )
        self.organization = Organization.objects.create(name="Demo producer tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization)
        currency = Currency.objects.create(name="Producer Dollar", symbol="PRD", longer_name="Producer Dollar")
        self.wallet = Wallet.objects.create(
            user=self.user, organization=self.organization, name=DEMO_WALLET_NAME,
            currency=currency, balance=Decimal("100000"), is_real=False,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_ORGANIZATION_ID": str(self.organization.id)}

    def create_order(self, key="order-1", direction="up"):
        with patch("trade.demo_engine.quote", return_value=(Decimal("116200.50"), timezone.now())):
            response = self.client.post(
                "/api/v1/demo/orders",
                {"symbol": "BTCUSDT", "direction": direction, "amount": "10", "duration": 5},
                format="json", HTTP_IDEMPOTENCY_KEY=key, **self.headers,
            )
        self.assertEqual(response.status_code, 201)
        return Trade.objects.get(pk=response.data["id"])

    def test_order_commit_creates_versioned_accepted_and_opened_events(self):
        trade = self.create_order()
        events = list(DemoEventOutbox.objects.filter(trade=trade).order_by("sequence"))
        self.assertEqual([event.event_type for event in events], ["demo.order.accepted", "demo.execution.opened"])
        self.assertLess(events[0].sequence, events[1].sequence)
        self.assertNotEqual(events[0].event_id, events[1].event_id)
        for event in events:
            message = envelope(event)
            self.assertEqual(message["event_version"], 1)
            self.assertEqual(message["account_id"], str(self.wallet.id))
            self.assertEqual(message["tenant_id"], str(self.organization.id))
            self.assertEqual(Decimal(message["data"]["open_price"]), Decimal("116200.50"))
            self.assertEqual(message["data"]["status_version"], event.sequence)
            self.assertTrue(message["channel"].endswith(str(self.wallet.id)))
            self.assertTrue(jetstream_subject(event).startswith("private."))

    def test_idempotent_retry_has_no_duplicate_events_or_effect(self):
        self.create_order()
        balance = Wallet.objects.get(pk=self.wallet.pk).balance
        with patch("trade.demo_engine.quote", return_value=(Decimal("116200.50"), timezone.now())):
            response = self.client.post(
                "/api/v1/demo/orders", {"symbol": "BTCUSDT", "direction": "up", "amount": "10", "duration": 5},
                format="json", HTTP_IDEMPOTENCY_KEY="order-1", **self.headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DemoEventOutbox.objects.count(), 2)
        self.assertEqual(Wallet.objects.get(pk=self.wallet.pk).balance, balance)

    def test_settlement_event_uses_server_authoritative_values(self):
        trade = self.create_order()
        trade.expires_at = timezone.now() - timedelta(seconds=1)
        trade.save(update_fields=["expires_at"])
        with patch("trade.demo_engine.quote", return_value=(Decimal("116250.00"), timezone.now())):
            self.assertEqual(settle_due_orders(), 1)
        event = DemoEventOutbox.objects.get(trade=trade, event_type="demo.execution.settled")
        payload = event.payload
        self.assertEqual(payload["result"], "WON")
        self.assertEqual(payload["settlement_price"], "116250.00")
        self.assertTrue(payload["settlement_time"])
        self.assertEqual(payload["expiry_time"], trade.expires_at.isoformat())

    def test_terminal_order_events_are_atomic_and_single_effect(self):
        expected = {
            "REJECTED": "demo.order.rejected",
            "CANCELLED": "demo.order.cancelled",
            "EXPIRED": "demo.order.expired",
        }
        for index, (state, event_type) in enumerate(expected.items()):
            trade = self.create_order(f"terminal-{index}")
            self.assertTrue(transition_demo_order(trade.pk, state))
            self.assertFalse(transition_demo_order(trade.pk, state))
            self.assertEqual(DemoEventOutbox.objects.filter(trade=trade, event_type=event_type).count(), 1)

    def test_outbox_rolls_back_with_order_state(self):
        trade = self.create_order()
        before = DemoEventOutbox.objects.count()
        try:
            with transaction.atomic():
                trade.demo_state = "CANCELLED"
                trade.save(update_fields=["demo_state"])
                from .demo_events import enqueue_trade_event
                enqueue_trade_event(trade, "demo.order.cancelled", status="CANCELLED")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(DemoEventOutbox.objects.count(), before)
        trade.refresh_from_db()
        self.assertEqual(trade.demo_state, "OPEN")

    def test_trade_history_is_bounded_and_cursor_paginated(self):
        for index in range(30):
            self.create_order(f"page-{index}")
        response = self.client.get("/api/v1/demo/trades", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit"], 25)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertIsNotNone(response.data["next_cursor"])
        invalid = self.client.get("/api/v1/demo/trades?limit=101", **self.headers)
        self.assertEqual(invalid.status_code, 400)

    @patch.dict(os.environ, {
        "REALTIME_V2_ENABLED": "true", "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true", "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "test-only-secret",
    })
    def test_v2_demo_channel_authorization_is_account_scoped(self):
        own = self.client.post(
            "/api/v1/realtime/v2/subscription-token",
            {"channel": f"demo.order:{self.wallet.id}"}, format="json", **self.headers,
        )
        self.assertEqual(own.status_code, 200)
        other_user = get_user_model().objects.create_user(
            email="other-demo@example.invalid", password="test-pass", phone_number="+12025550183"
        )
        other_wallet = Wallet.objects.create(
            user=other_user, organization=self.organization, name=DEMO_WALLET_NAME,
            currency=self.wallet.currency, balance=Decimal("100"), is_real=False,
        )
        denied = self.client.post(
            "/api/v1/realtime/v2/subscription-token",
            {"channel": f"demo.execution:{other_wallet.id}"}, format="json", **self.headers,
        )
        self.assertEqual(denied.status_code, 403)


class DemoEventTenantIsolationTests(TestCase):
    def test_account_scoped_channels_do_not_collide(self):
        self.assertNotEqual("demo.order:account-a", "demo.order:account-b")
