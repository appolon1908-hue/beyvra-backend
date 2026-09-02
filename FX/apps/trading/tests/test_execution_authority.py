from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent
from apps.trading.execution_authority import preview_route, record_ambiguous_outcome, record_quality, seed_safe_authorities
from apps.trading.models import ExecutionProviderRecord, ExecutionRoutingDecision, TradingOrder


@override_settings(REAL_TRADING_ENABLED=False, EXTERNAL_EXECUTION_ENABLED=False, LIVE_BROKER_ROUTING_ENABLED=False,
    FIX_LIVE_SESSION_ENABLED=False, PAPER_TRADING_ALLOWED=True, SIMULATION_ALLOWED=True)
class ExecutionAuthorityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="route@example.test", password="x", phone_number="+15550000001")
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def payload(self, **extra):
        return {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "2", "reference_price": "100", "mode": "SIMULATION", **extra}

    def test_preview_selects_only_simulation_and_has_evidence(self):
        response = self.client.post("/api/v1/execution/preview", self.payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_provider_id"], "simulation")
        self.assertEqual(response.data["outbound_live_execution_requests"], 0)
        self.assertEqual(len(response.data["request_hash"]), 64)

    def test_live_always_fails_closed(self):
        response = self.client.post("/api/v1/execution/preview", self.payload(mode="LIVE"), format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(ExecutionRoutingDecision.objects.count(), 0)

    @override_settings(LIVE_BROKER_ROUTING_ENABLED=True)
    def test_unsafe_runtime_configuration_denies_even_simulation(self):
        with self.assertRaisesMessage(ValueError, "LIVE_EXECUTION_DISABLED"):
            preview_route(self.user, self.payload())

    def test_halted_provider_is_excluded_and_no_failover(self):
        provider = seed_safe_authorities(); provider.health = "HALTED"; provider.enabled = False; provider.save()
        result = preview_route(self.user, self.payload())
        self.assertEqual(result["decision"], "DENIED")
        self.assertIn("PROVIDER_DISABLED", result["exclusions"][0]["reasons"])

    def test_quality_is_side_aware(self):
        order = TradingOrder.objects.create(tenant_ref="default", subject_ref=str(self.user.pk), account_ref="sim:x", instrument_id="BTC-USD",
            order_type="MARKET", side="BUY", quantity=2, filled_quantity=2, average_fill_price=Decimal("101"), simulation=True)
        preview_route(self.user, self.payload(), persist=True, order=order)
        quality = record_quality(order)
        self.assertEqual(quality.slippage_bps, Decimal("100"))
        self.assertEqual(quality.price_improvement_amount, Decimal("-1"))

    def test_operator_halt_resume_requires_admin_and_audits(self):
        provider = seed_safe_authorities()
        denied = self.client.post("/api/v1/operator/execution/providers/simulation/halt", {"reason": "test"}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.user.is_staff = True; self.user.is_superuser = True; self.user.save(); self.client.force_authenticate(self.user)
        halted = self.client.post("/api/v1/operator/execution/providers/simulation/halt", {"reason": "drill"}, format="json",
            HTTP_IDEMPOTENCY_KEY="halt-key", HTTP_IF_MATCH=provider.updated_at.isoformat())
        self.assertEqual(halted.data["health"], "HALTED")
        resumed = self.client.post("/api/v1/operator/execution/providers/simulation/resume", {"reason": "verified"}, format="json",
            HTTP_IDEMPOTENCY_KEY="resume-key", HTTP_IF_MATCH=halted.data["version"])
        self.assertEqual(resumed.data["health"], "HEALTHY")
        self.assertEqual(ApplicationAuditEvent.objects.filter(resource_type="execution_provider").count(), 2)

    def test_operator_control_requires_command_headers_and_replays_once(self):
        provider = seed_safe_authorities()
        self.user.is_superuser = True; self.user.save(); self.client.force_authenticate(self.user)
        url = "/api/v1/operator/execution/providers/simulation/halt"
        self.assertEqual(self.client.post(url, {"reason": "drill"}, format="json").status_code, 422)
        headers = {"HTTP_IDEMPOTENCY_KEY": "same-halt", "HTTP_IF_MATCH": provider.updated_at.isoformat()}
        first = self.client.post(url, {"reason": "drill"}, format="json", **headers)
        replay = self.client.post(url, {"reason": "drill"}, format="json", **headers)
        self.assertEqual((first.status_code, replay.status_code), (200, 200))
        self.assertEqual(first.data, replay.data)
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="execution.provider.halted").count(), 1)

    def test_operator_control_rejects_stale_version_and_semantic_key_reuse(self):
        provider = seed_safe_authorities()
        self.user.is_superuser = True; self.user.save(); self.client.force_authenticate(self.user)
        url = "/api/v1/operator/execution/providers/simulation/halt"
        stale = self.client.post(url, {"reason": "drill"}, format="json", HTTP_IDEMPOTENCY_KEY="stale", HTTP_IF_MATCH="old")
        self.assertEqual(stale.status_code, 409)
        provider.refresh_from_db(); self.assertEqual(provider.health, "HEALTHY")
        headers = {"HTTP_IDEMPOTENCY_KEY": "semantic", "HTTP_IF_MATCH": provider.updated_at.isoformat()}
        self.assertEqual(self.client.post(url, {"reason": "first"}, format="json", **headers).status_code, 200)
        conflict = self.client.post(url, {"reason": "different"}, format="json", **headers)
        self.assertEqual(conflict.status_code, 409)

    def test_tenant_isolation_for_route_and_quality(self):
        other = get_user_model().objects.create_user(email="other@example.test", password="x", phone_number="+15550000002")
        order = TradingOrder.objects.create(tenant_ref="default", subject_ref=str(other.pk), account_ref="sim:y", instrument_id="BTC-USD",
            order_type="MARKET", side="BUY", quantity=1, filled_quantity=1, average_fill_price=100, simulation=True)
        preview_route(other, self.payload(quantity="1"), persist=True, order=order)
        self.assertEqual(self.client.get(f"/api/v1/execution/routes/{order.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/execution/quality/{order.id}").status_code, 404)

    def test_capabilities_and_venues_never_advertise_live(self):
        ExecutionProviderRecord.objects.create(provider_id="live-fixture", display_name="Never", mode="LIVE", enabled=False, health="HALTED")
        self.assertNotIn("live-fixture", str(self.client.get("/api/v1/execution/capabilities").data))
        self.assertEqual(self.client.get("/api/v1/execution/venues").status_code, 200)

    def test_unknown_outcome_prohibits_retry_and_failover(self):
        order = TradingOrder.objects.create(tenant_ref="default", subject_ref=str(self.user.pk), account_ref="sim:x", instrument_id="BTC-USD",
            order_type="MARKET", side="BUY", quantity=1, simulation=True)
        preview_route(self.user, self.payload(quantity="1"), persist=True, order=order)
        unknown = record_ambiguous_outcome(order, "simulation")
        self.assertEqual(unknown.status, "UNKNOWN")
        self.assertIn("FAILOVER_PROHIBITED", unknown.exclusion_reasons[0]["reasons"])
