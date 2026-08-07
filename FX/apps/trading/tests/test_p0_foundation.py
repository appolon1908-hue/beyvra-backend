import os
import importlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent, TradingControl
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, claim_outbox_batch, consume_once, enqueue_event, mark_publish_result
from apps.compliance import ComplianceEligibility, KycStatus
from apps.compliance.domain import ScreeningStatus
from apps.trading.domain.orders import InvalidOrderTransition, OrderState, transition_order
from apps.trading.models import TradingOrder
from apps.trading.repositories import transition_persisted_order
from apps.trading.risk import RiskEngine
from integrations.financial.client import FinancialClient
from integrations.financial.exceptions import FinancialMutationDisabled
from real_wallet.models import FeatureFlag
from real_wallet.services import is_feature_enabled
from users.models import User


class OrderAndRiskTests(TestCase):
    def test_compliance_lifecycle_keeps_eligibility_dimensions_separate(self):
        eligibility = ComplianceEligibility(
            kyc_status=KycStatus.APPROVED,
            aml_status=ScreeningStatus.CLEARED,
            sanctions_status=ScreeningStatus.CLEARED,
            trading_eligible=True,
            deposit_eligible=False,
            withdrawal_eligible=False,
        )
        self.assertTrue(eligibility.permits_trading())
        self.assertFalse(eligibility.deposit_eligible)
        self.assertFalse(eligibility.withdrawal_eligible)

    def test_transition_matrix_and_terminal_states(self):
        self.assertEqual(transition_order("PENDING", "ACCEPTED"), OrderState.ACCEPTED)
        self.assertEqual(transition_order("OPEN", "FILLED"), OrderState.FILLED)
        with self.assertRaises(InvalidOrderTransition):
            transition_order("FILLED", "OPEN")

    def test_risk_allow_deny_review_and_stale(self):
        engine = RiskEngine()
        base = {"compliance_eligible": True, "quantity": "1", "min_quantity": "0.1", "notional": "10", "available_funds": "20", "provider_health": "HEALTHY"}
        self.assertEqual(engine.evaluate_order(base).decision, "ALLOW")
        denied = engine.evaluate_order({**base, "market_data_stale": True})
        self.assertEqual(denied.decision, "DENY")
        self.assertIn("MARKET_DATA_STALE", denied.reason_codes)
        self.assertEqual(engine.evaluate_order({**base, "manual_review_required": True}).decision, "REVIEW")
        self.assertEqual(engine.evaluate_order({**base, "control_state": "HALTED"}).decision, "DENY")

    def test_risk_limits_and_price_bands_deny(self):
        result = RiskEngine().evaluate_order(
            {
                "compliance_eligible": True,
                "quantity": "11",
                "max_quantity": "10",
                "notional": "110",
                "available_funds": "1000",
                "daily_notional": "950",
                "daily_notional_limit": "1000",
                "reference_price": "10",
                "order_price": "12",
                "price_band_percent": "5",
            }
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(
            set(result.reason_codes),
            {"QUANTITY_OUT_OF_RANGE", "DAILY_NOTIONAL_LIMIT", "PRICE_BAND_EXCEEDED"},
        )


class CanonicalTradingApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="p0@example.invalid", phone_number="+12025550991", password="test")
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_real_mutations_fail_closed_with_canonical_error(self):
        for path in ("/api/v1/trading/orders/preview", "/api/v1/trading/orders", f"/api/v1/trading/orders/{uuid.uuid4()}/cancel"):
            response = self.client.post(path, {}, format="json")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "FEATURE_DISABLED")

    def test_real_reads_are_empty_not_fake(self):
        for path in ("/api/v1/trading/orders", "/api/v1/trading/trades", "/api/v1/trading/positions", "/api/v1/trading/accounts", "/api/v1/trading/fees"):
            self.assertEqual(self.client.get(path).status_code, 200)


class ControlAndCompatibilityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="p0-admin@example.invalid",
            phone_number="+12025550992",
            password="test",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_halt_is_idempotent_and_immutably_audited(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "halt-1", "HTTP_X_REQUEST_ID": "request-1"}
        first = self.client.post(
            "/api/v1/admin/trading/halt", {"reason": "risk exercise"}, format="json", **headers
        )
        replay = self.client.post(
            "/api/v1/admin/trading/halt", {"reason": "risk exercise"}, format="json", **headers
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(TradingControl.objects.count(), 1)
        self.assertEqual(ApplicationAuditEvent.objects.count(), 1)

    def test_legacy_route_emits_deprecation_contract(self):
        response = self.client.get("/api/wallet/currencies/")
        self.assertEqual(response.headers["Deprecation"], "true")
        self.assertIn("successor-version", response.headers["Link"])
        self.assertIn("Sunset", response.headers)

    def test_health_contracts(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        with override_settings(NATS_JETSTREAM_ENABLED=False):
            ready = self.client.get("/health/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(ready.json()["status"], "ready")
        with override_settings(NATS_JETSTREAM_ENABLED=True):
            unavailable = self.client.get("/health/ready")
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(unavailable.json()["checks"]["nats"], "worker_unavailable")


class OutboxInboxTests(TestCase):
    def test_domain_mutation_and_outbox_roll_back_together(self):
        try:
            with transaction.atomic():
                enqueue_event(aggregate_type="order", aggregate_id="1", event_type="trading.order.created.v1", payload={}, tenant_ref="t")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_retry_and_dead_letter(self):
        row = enqueue_event(aggregate_type="order", aggregate_id="1", event_type="trading.order.created.v1", payload={}, tenant_ref="t")
        claimed = claim_outbox_batch()
        self.assertEqual(claimed, [row])
        row = mark_publish_result(row, error_code="TimeoutError", maximum_attempts=1)
        self.assertEqual(row.state, OutboxEvent.State.DEAD_LETTER)
        self.assertNotIn("password", row.last_error.lower())

    def test_duplicate_consumer_has_one_effect(self):
        effects = []
        envelope = {"event_id": str(uuid.uuid4()), "payload": {"x": 1}}
        self.assertTrue(consume_once(envelope=envelope, consumer_name="test", mutation=lambda: effects.append(1)))
        self.assertFalse(consume_once(envelope=envelope, consumer_name="test", mutation=lambda: effects.append(1)))
        self.assertEqual(effects, [1])
        self.assertEqual(ProcessedEvent.objects.count(), 1)


class IdempotencyConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_100_concurrent_same_key_creates_one_record(self):
        barrier = threading.Barrier(20)
        def attempt(_index):
            close_old_connections(); barrier.wait()
            record, created = begin_idempotent_request(key="same", tenant_ref="t", actor_ref="a", endpoint="/orders", method="POST", request_data={"quantity": "1"})
            close_old_connections(); return record.pk, created
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(attempt, range(100)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({pk for pk, _ in results}), 1)

    def test_same_key_different_payload_conflicts(self):
        begin_idempotent_request(key="k", tenant_ref="t", actor_ref="a", endpoint="/orders", method="POST", request_data={"x": 1})
        with self.assertRaises(IdempotencyConflict):
            begin_idempotent_request(key="k", tenant_ref="t", actor_ref="a", endpoint="/orders", method="POST", request_data={"x": 2})

    def test_concurrent_inbox_delivery_has_one_database_effect(self):
        event_id = str(uuid.uuid4())
        envelope = {"event_id": event_id, "payload": {"order_id": "one"}}
        barrier = threading.Barrier(10)

        def consume(_index):
            close_old_connections()
            barrier.wait()
            result = consume_once(
                envelope=envelope,
                consumer_name="concurrent-test",
                mutation=lambda: OutboxEvent.objects.create(
                    aggregate_type="test",
                    aggregate_id=str(uuid.uuid4()),
                    event_type="test.effect.created.v1",
                    payload={},
                    tenant_ref="test",
                    correlation_id=uuid.uuid4(),
                    occurred_at=timezone.now(),
                ),
            )
            close_old_connections()
            return result

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(consume, range(10)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_concurrent_order_fill_and_cancel_leave_valid_state(self):
        order = TradingOrder.objects.create(
            tenant_ref="t",
            subject_ref="s",
            account_ref="a",
            instrument_id="BTC-USD",
            order_type="MARKET",
            side="BUY",
            quantity="1",
            state="OPEN",
        )
        barrier = threading.Barrier(2)

        def transition(target):
            close_old_connections()
            barrier.wait()
            try:
                transition_persisted_order(order.pk, target)
            except InvalidOrderTransition:
                pass
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(transition, ("FILLED", "CANCEL_PENDING")))
        order.refresh_from_db()
        self.assertIn(order.state, {"FILLED", "CANCEL_PENDING"})


class SafetyBoundaryTests(TestCase):
    def test_beyvra_public_identity_defaults_are_explicit(self):
        self.assertEqual(settings.PUBLIC_BRAND_NAME, "Beyvra")
        self.assertEqual(settings.PUBLIC_SITE_URL, "https://beyvra.com")
        self.assertEqual(settings.PUBLIC_API_URL, "https://api.beyvra.com")
        self.assertEqual(settings.PUBLIC_WS_URL, "wss://api.beyvra.com/ws/v2/")
        self.assertEqual(settings.PUBLIC_STATUS_URL, "https://api.beyvra.com/health/ready")
        self.assertNotIn("codestra.cloud", settings.GOOGLE_OIDC_REDIRECT_URI)

    def test_financial_database_alias_and_credentials_are_absent(self):
        self.assertEqual(set(settings.DATABASES), {"default"})
        forbidden = {"FINANCIAL_DB_HOST", "FINANCIAL_DB_NAME", "FINANCIAL_DB_PASSWORD", "FINANCIAL_DATABASE_URL"}
        self.assertFalse(forbidden.intersection(os.environ))

    def test_financial_mutations_are_disabled_without_transport(self):
        client = FinancialClient.__new__(FinancialClient)
        with self.assertRaises(FinancialMutationDisabled):
            client.reserve_funds()

    def test_database_flag_cannot_bypass_application_real_money_kill_switch(self):
        FeatureFlag.objects.update_or_create(
            key="real_wallet_deposits_enabled", defaults={"enabled": True}
        )
        self.assertFalse(is_feature_enabled("real_wallet_deposits_enabled"))

    def test_production_test_otp_route_is_not_resolved(self):
        from users import google_urls

        with override_settings(API_ENV="production"):
            production_urls = importlib.reload(google_urls)
            self.assertNotIn("test/otp", {str(pattern.pattern) for pattern in production_urls.urlpatterns})
        importlib.reload(google_urls)
