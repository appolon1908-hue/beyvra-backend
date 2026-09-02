import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent
from apps.surveillance.engine import SurveillanceEngine
from apps.surveillance.models import SurveillanceAudit, SurveillanceCase, SurveillanceCaseEvent, SurveillanceDeadLetter, SurveillanceEvent, SurveillanceRule, TradingRestriction
from apps.surveillance.reconciliation import reconcile_surveillance
from apps.surveillance.services import ingest_event
from apps.trading.application.simulation import create
from apps.trading.models import SimulatedTrade, TradingOrder
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership
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
        organization = Organization.objects.create(name="Surveillance Test Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=organization)
        ComplianceProfile.objects.create(user=self.user, organization=organization, account_state=AccountState.ACTIVE, kyc_state=KycState.APPROVED, aml_state=AmlState.CLEARED, sanctions_state=SanctionsState.CLEAR, jurisdiction_state=JurisdictionState.SUPPORTED)
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
        request_payload = {"scope_type": "ACCOUNT", "scope_ref": "sim:target", "restriction_type": "BLOCK_NEW_ORDERS", "reason": "synthetic review"}
        create_headers = {"HTTP_IDEMPOTENCY_KEY": "restriction-create", "HTTP_X_REQUEST_ID": "restriction-create-request"}
        response = client.post("/api/v1/operator/surveillance/restrictions", request_payload, format="json", **create_headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(client.post("/api/v1/operator/surveillance/restrictions", request_payload, format="json", **create_headers).json(), response.json())
        self.assertEqual(TradingRestriction.objects.count(), 1)
        restriction_id = response.json()["id"]
        self_approval = client.post(f"/api/v1/operator/surveillance/restrictions/{restriction_id}/approve", {"reason": "approve"}, format="json")
        self.assertEqual(self_approval.status_code, 403)
        self.assertNotIn("request_id", str(self_approval.json()).lower())
        client.force_authenticate(self.checker)
        approval_headers = {"HTTP_IDEMPOTENCY_KEY": "restriction-approve", "HTTP_X_REQUEST_ID": "restriction-approve-request", "HTTP_IF_MATCH": response.json()["version"]}
        approved = client.post(f"/api/v1/operator/surveillance/restrictions/{restriction_id}/approve", {"reason": "independent"}, format="json", **approval_headers)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(client.post(f"/api/v1/operator/surveillance/restrictions/{restriction_id}/approve", {"reason": "independent"}, format="json", **approval_headers).json(), approved.json())
        self.assertEqual(OutboxEvent.objects.filter(aggregate_id=restriction_id, event_type="regulatory.surveillance.restriction.applied.v1").count(), 1)
        customer = APIClient(); customer.force_authenticate(self.user)
        self.assertEqual(customer.get("/api/v1/operator/surveillance/rules").status_code, 403)
        self.assertEqual(customer.get(f"/api/v1/operator/surveillance/events/{uuid.uuid4()}").status_code, 403)

    def test_surveillance_case_commands_require_version_replay_once_and_use_independent_resolution(self):
        row = SurveillanceCase.objects.create(tenant_ref="default", account_ref="sim:target", case_type="MARKET_ABUSE_REVIEW", severity="CRITICAL", status="OPEN", opened_at=self.now, policy_version="surveillance-2026-08-v1", evidence_hash="3" * 64)
        maker = APIClient(); maker.force_authenticate(self.manager); base=f"/api/v1/operator/surveillance/cases/{row.pk}"
        self.assertEqual(maker.post(f"{base}/assign", {"reason":"ownership"}, format="json").status_code, 422)
        self.assertEqual(maker.post(f"{base}/assign", {"reason":"ownership"}, format="json", HTTP_IDEMPOTENCY_KEY="k"*256, HTTP_X_REQUEST_ID="request", HTTP_IF_MATCH=row.updated_at.isoformat()).status_code, 422)
        self.assertTrue({"idempotency-key", "x-request-id", "if-match"}.issubset(settings.CORS_ALLOW_HEADERS))
        stale = maker.post(f"{base}/assign", {"reason":"ownership"}, format="json", HTTP_IDEMPOTENCY_KEY="case-stale", HTTP_X_REQUEST_ID="case-stale-request", HTTP_IF_MATCH="stale")
        self.assertEqual(stale.status_code, 409); row.refresh_from_db(); self.assertEqual(row.status, "OPEN")
        headers={"HTTP_IDEMPOTENCY_KEY":"case-assign","HTTP_X_REQUEST_ID":"case-assign-request","HTTP_IF_MATCH":row.updated_at.isoformat()}
        assigned=maker.post(f"{base}/assign", {"reason":"ownership"}, format="json", **headers); replay=maker.post(f"{base}/assign", {"reason":"ownership"}, format="json", **headers)
        self.assertEqual((assigned.status_code,replay.status_code),(200,200)); self.assertEqual(assigned.json(),replay.json()); self.assertEqual(SurveillanceCaseEvent.objects.filter(case=row,event_type="CASE_ASSIGNED").count(),1)
        self_resolve=maker.post(f"{base}/resolve", {"reason":"reviewed"}, format="json", HTTP_IDEMPOTENCY_KEY="self-resolve", HTTP_X_REQUEST_ID="self-resolve-request", HTTP_IF_MATCH=assigned.json()["version"])
        self.assertEqual(self_resolve.status_code,403)
        checker=APIClient(); checker.force_authenticate(self.checker); resolved=checker.post(f"{base}/resolve", {"reason":"independent review","resolution_code":"NO_ACTION"}, format="json", HTTP_IDEMPOTENCY_KEY="case-resolve", HTTP_X_REQUEST_ID="case-resolve-request", HTTP_IF_MATCH=assigned.json()["version"])
        self.assertEqual(resolved.status_code,200); row.refresh_from_db(); self.assertEqual(row.status,"RESOLVED")
        self.assertEqual(ApplicationAuditEvent.objects.filter(resource_id=str(row.pk),action="surveillance.case.resolve").count(),1)

    def test_restriction_command_rejects_semantic_conflict_and_removal_replays_once(self):
        client=APIClient(); client.force_authenticate(self.manager); endpoint="/api/v1/operator/surveillance/restrictions"; headers={"HTTP_IDEMPOTENCY_KEY":"semantic-restriction","HTTP_X_REQUEST_ID":"semantic-request"}
        payload={"scope_type":"ACCOUNT","scope_ref":"sim:target","restriction_type":"BLOCK_NEW_ORDERS","reason":"documented review"}
        created=client.post(endpoint,payload,format="json",**headers); self.assertEqual(created.status_code,201)
        conflict=client.post(endpoint,{**payload,"reason":"different reason"},format="json",**headers); self.assertEqual(conflict.status_code,409)
        rid=created.json()["id"]; checker=APIClient(); checker.force_authenticate(self.checker)
        approved=checker.post(f"{endpoint}/{rid}/approve",{"reason":"independent approval"},format="json",HTTP_IDEMPOTENCY_KEY="approve-for-remove",HTTP_X_REQUEST_ID="approve-for-remove-request",HTTP_IF_MATCH=created.json()["version"]); self.assertEqual(approved.status_code,200)
        remove_headers={"HTTP_IDEMPOTENCY_KEY":"remove-once","HTTP_X_REQUEST_ID":"remove-request","HTTP_IF_MATCH":approved.json()["version"]}
        removed=client.post(f"{endpoint}/{rid}/remove",{"reason":"restriction no longer required"},format="json",**remove_headers); replay=client.post(f"{endpoint}/{rid}/remove",{"reason":"restriction no longer required"},format="json",**remove_headers)
        self.assertEqual((removed.status_code,replay.status_code),(200,200)); self.assertEqual(removed.json(),replay.json()); self.assertEqual(OutboxEvent.objects.filter(aggregate_id=rid,event_type="regulatory.surveillance.restriction.removed.v1").count(),1)

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
