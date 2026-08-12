import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.foundation.models import OutboxEvent, ProcessedEvent
from apps.surveillance.engine import SurveillanceEngine
from apps.surveillance.models import SurveillanceAudit, SurveillanceCase, SurveillanceDeadLetter, SurveillanceEvent, SurveillanceRule, TradingRestriction
from apps.surveillance.reconciliation import reconcile_surveillance
from apps.surveillance.services import ingest_event
from apps.trading.application.simulation import create
from apps.trading.models import SimulatedTrade, TradingOrder
from users.models import User


@override_settings(SIMULATED_TRADING_ENABLED=True, DEPLOYMENT_ENV="test", SIMULATED_EXECUTION_INLINE=False, SURVEILLANCE_ENABLED=True, SELF_TRADE_PREVENTION_ENABLED=True)
class SurveillanceTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        SurveillanceRule.objects.all().delete()
        definitions = [
            ("stp-v1", "SELF_TRADE_ATTEMPT", "CRITICAL", {}),
            ("restricted-v1", "RESTRICTED_INSTRUMENT_ATTEMPT", "HIGH", {}),
            ("wash-v1", "WASH_TRADE_PATTERN", "HIGH", {"minimum_trades": 4, "max_net_ratio": "0.1"}),
            ("spoof-v1", "SPOOFING_INDICATOR", "HIGH", {}),
            ("layer-v1", "LAYERING_INDICATOR", "HIGH", {"minimum_levels": 3}),
            ("cancel-v1", "EXCESSIVE_CANCEL_PATTERN", "MEDIUM", {"minimum_orders": 5, "cancel_ratio": "0.8"}),
            ("flip-v1", "RAPID_ORDER_FLIP", "MEDIUM", {"window_seconds": 30}),
            ("rate-v1", "ORDER_RATE_ANOMALY", "MEDIUM", {"orders_per_window": 20}),
        ]
        for name, event_type, severity, parameters in definitions:
            SurveillanceRule.objects.create(name=name, event_type=event_type, severity=severity, parameters_json_safe=parameters, policy_version="surveillance-2026-08-v1", effective_from=self.now)
        self.user = User.objects.create_user(email="trader@example.test", password="safe-password", phone_number="+15550000001")
        self.manager = User.objects.create_user(email="manager@example.test", password="safe-password", phone_number="+15550000002")
        self.checker = User.objects.create_user(email="checker@example.test", password="safe-password", phone_number="+15550000003")
        group, _ = Group.objects.get_or_create(name="surveillance_manager")
        self.manager.groups.add(group); self.checker.groups.add(group)

    def payload(self, side="BUY"):
        return {"instrument": "BTC-USD", "side": side, "order_type": "MARKET", "quantity": "0.01"}

    def test_self_trade_prevention_rejects_before_second_order_or_execution(self):
        first, _ = create(self.user, self.payload("BUY"), "first-order")
        with self.assertRaisesRegex(ValueError, "ORDER_REJECTED"):
            create(self.user, self.payload("SELL"), "crossing-order")
        self.assertEqual(TradingOrder.objects.count(), 1)
        self.assertEqual(SimulatedTrade.objects.count(), 0)
        event = SurveillanceEvent.objects.get(event_type="SELF_TRADE_ATTEMPT")
        self.assertEqual(event.account_ref, f"sim:{self.user.pk}")
        self.assertEqual(SurveillanceCase.objects.filter(events=event).count(), 1)
        self.assertTrue(OutboxEvent.objects.filter(aggregate_id=str(event.id)).exists())

    def test_restriction_precedence_denies_before_order_creation(self):
        restriction = TradingRestriction.objects.create(tenant_ref="default", scope_type="INSTRUMENT", scope_ref="BTC-USD", restriction_type="BLOCK_INSTRUMENT", reason_code="INTERNAL_REVIEW", effective_from=self.now, created_by="maker", approved_by="checker", status="ACTIVE")
        SurveillanceAudit.objects.create(tenant_ref="default", actor_ref="checker", action="surveillance.restriction.approved", resource_type="trading_restriction", resource_ref=str(restriction.id), reason="fixture", evidence_hash="0" * 64, occurred_at=self.now)
        with self.assertRaisesRegex(ValueError, "TRADING_NOT_AVAILABLE"):
            create(self.user, self.payload(), "restricted-order")
        self.assertEqual(TradingOrder.objects.count(), 0)
        self.assertEqual(SurveillanceEvent.objects.filter(event_type="RESTRICTED_INSTRUMENT_ATTEMPT").count(), 1)

    def test_window_indicators_are_deterministic_and_indicator_only(self):
        events = []
        for index in range(20):
            events.append({"kind": "ORDER", "side": "BUY" if index % 2 == 0 else "SELL", "quantity": "1", "at": self.now + timedelta(seconds=index)})
        for index in range(16):
            events.append({"kind": "CANCEL", "side": "BUY", "quantity": "1", "price": str(100 + index % 3), "large": True, "rapid": True, "at": self.now + timedelta(seconds=index, milliseconds=500)})
        for index in range(4):
            events.append({"kind": "TRADE", "side": "BUY" if index % 2 == 0 else "SELL", "quantity": "1", "at": self.now + timedelta(seconds=index + 20)})
        findings = SurveillanceEngine().evaluate_window(events)
        types = {finding.event_type for finding in findings}
        self.assertTrue({"WASH_TRADE_PATTERN", "SPOOFING_INDICATOR", "LAYERING_INDICATOR", "EXCESSIVE_CANCEL_PATTERN", "RAPID_ORDER_FLIP", "ORDER_RATE_ANOMALY"}.issubset(types))
        self.assertNotIn("CONFIRMED_MANIPULATION", types)

    def test_inbox_is_idempotent_and_poison_event_dead_letters(self):
        event_id = uuid.uuid4()
        envelope = {"event_id": str(event_id), "event_type": "order.created", "tenant_ref": "default", "payload": {"account_ref": "sim:1", "instrument": "BTC-USD", "window_events": []}}
        self.assertTrue(ingest_event(envelope))
        self.assertFalse(ingest_event(envelope))
        self.assertEqual(ProcessedEvent.objects.filter(event_id=event_id, consumer_name="surveillance-v1").count(), 1)
        poison = {"event_id": "not-a-uuid", "event_type": "order.created", "tenant_ref": "default", "payload": {}}
        with self.assertRaises(ValueError): ingest_event(poison)
        self.assertEqual(SurveillanceDeadLetter.objects.count(), 1)

    def test_operator_rbac_tenant_scope_maker_checker_and_safe_errors(self):
        client = APIClient(); client.force_authenticate(self.manager)
        response = client.post("/api/v1/operator/surveillance/restrictions", {"scope_type": "ACCOUNT", "scope_ref": "sim:target", "restriction_type": "BLOCK_NEW_ORDERS", "reason": "synthetic review"}, format="json")
        self.assertEqual(response.status_code, 201)
        restriction_id = response.json()["id"]
        self_approval = client.post(f"/api/v1/operator/surveillance/restrictions/{restriction_id}/approve", {"reason": "approve"}, format="json")
        self.assertEqual(self_approval.status_code, 403)
        self.assertNotIn("request_id", str(self_approval.json()).lower())
        client.force_authenticate(self.checker)
        self.assertEqual(client.post(f"/api/v1/operator/surveillance/restrictions/{restriction_id}/approve", {"reason": "independent"}, format="json").status_code, 200)
        customer = APIClient(); customer.force_authenticate(self.user)
        self.assertEqual(customer.get("/api/v1/operator/surveillance/rules").status_code, 403)
        self.assertEqual(customer.get(f"/api/v1/operator/surveillance/events/{uuid.uuid4()}").status_code, 403)

    def test_audit_is_immutable_and_reconciliation_passes(self):
        first, _ = create(self.user, self.payload("BUY"), "audit-first")
        with self.assertRaisesRegex(ValueError, "ORDER_REJECTED"): create(self.user, self.payload("SELL"), "audit-cross")
        audit = SurveillanceAudit.objects.first()
        audit.reason = "tampered"
        with self.assertRaisesRegex(ValueError, "APPEND_ONLY"): audit.save()
        event = SurveillanceEvent.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            SurveillanceEvent.objects.filter(pk=event.pk).update(evidence_hash="f" * 64)
        self.assertEqual(reconcile_surveillance()["status"], "PASS")

    def test_disabled_surveillance_fails_closed(self):
        with self.settings(SURVEILLANCE_ENABLED=False):
            with self.assertRaisesRegex(ValueError, "SURVEILLANCE_TEMPORARILY_UNAVAILABLE"):
                create(self.user, self.payload(), "unavailable")
        self.assertEqual(TradingOrder.objects.count(), 0)
