import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent, TradingControl
from apps.foundation.checks import financial_database_isolation
from apps.trading.application.simulation import apply_execution, cancel, create, process_created_order
from apps.trading.domain.orders import OrderState, TRANSITIONS, InvalidOrderTransition, transition_order
from apps.trading.models import RiskDecision, SimulatedPosition, SimulatedReservation, SimulatedTrade, TradingOrder
from integrations.execution.simulated import SimulatedExecution, SimulatedExecutionProvider
from users.models import User
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test", SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False, EXTERNAL_EXECUTION_ENABLED=False, REAL_MONEY_ENABLED=False,
    SIMULATED_EXECUTION_PRICES={"BTC-USD": "100.00"}, SIMULATED_EXECUTION_INLINE=False,
)


def approve_for_simulation(user, label):
    organization = Organization.objects.create(name=f"{label} {uuid.uuid4()}")
    OrganizationMembership.objects.create(user=user, organization=organization)
    ComplianceProfile.objects.create(user=user, organization=organization, account_state=AccountState.ACTIVE, kyc_state=KycState.APPROVED, aml_state=AmlState.CLEARED, sanctions_state=SanctionsState.CLEAR, jurisdiction_state=JurisdictionState.SUPPORTED)


@SIMULATION
class SimulatedTradingE2ETests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email=f"sim-{uuid.uuid4()}@example.invalid", phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}", password="test")
        organization = Organization.objects.create(name=f"Simulation Test {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=organization)
        ComplianceProfile.objects.create(user=self.user, organization=organization, account_state=AccountState.ACTIVE, kyc_state=KycState.APPROVED, aml_state=AmlState.CLEARED, sanctions_state=SanctionsState.CLEAR, jurisdiction_state=JurisdictionState.SUPPORTED)
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_BEYVRA_SIMULATION_MODE": "true"}
        self.payload = {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "10"}

    def post_order(self, payload=None, key=None):
        return self.client.post("/api/v1/trading/orders", payload or self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()), **self.headers)

    def test_simulation_is_separate_and_requires_explicit_authority(self):
        denied = self.client.post("/api/v1/trading/orders/preview", self.payload, format="json")
        self.assertEqual(denied.status_code, 503)
        preview = self.client.post("/api/v1/trading/orders/preview", self.payload, format="json", **self.headers)
        self.assertEqual(preview.status_code, 200); self.assertEqual(preview.json()["decision"], "ALLOW"); self.assertTrue(preview.json()["simulation"])
        self.assertEqual(TradingOrder.objects.count(), 0); self.assertEqual(SimulatedReservation.objects.count(), 0); self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_order_creation_is_atomic_with_risk_reservation_outbox_and_audit(self):
        response = self.post_order()
        self.assertEqual(response.status_code, 201)
        order = TradingOrder.objects.get(pk=response.json()["id"])
        self.assertTrue(order.simulation); self.assertIsNotNone(order.risk_decision_id); self.assertIsNotNone(order.reservation_id)
        self.assertEqual(RiskDecision.objects.filter(order_id=order.id, decision="ALLOW").count(), 1)
        self.assertEqual(SimulatedReservation.objects.filter(order_id=order.id).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(aggregate_id=str(order.id), event_type="trading.order.created.v1").count(), 1)
        self.assertEqual(ApplicationAuditEvent.objects.filter(resource_id=str(order.id), context__simulation=True).count(), 1)

    def test_immediate_full_fill_settles_once_and_projects_balance_position(self):
        order = TradingOrder.objects.get(pk=self.post_order().json()["id"])
        process_created_order(order.id, "IMMEDIATE_FULL_FILL"); order.refresh_from_db()
        self.assertEqual(order.state, "FILLED"); self.assertEqual(order.filled_quantity, Decimal("10"))
        self.assertEqual(SimulatedTrade.objects.filter(order=order).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type="trading.execution.received.v1", payload__order_id=str(order.id)).count(), 1)
        position = SimulatedPosition.objects.get(instrument_id="BTC-USD"); self.assertEqual(position.quantity, Decimal("10"))
        account = position.account; self.assertEqual(account.total_balance, Decimal("8999"))
        self.assertEqual(SimulatedReservation.objects.get(order_id=order.id).state, "CONSUMED")

    def test_partial_four_then_six_has_exact_effects_and_no_overfill(self):
        order = TradingOrder.objects.get(pk=self.post_order().json()["id"])
        process_created_order(order.id, "PARTIAL_THEN_FILL"); order.refresh_from_db()
        self.assertEqual(order.state, "FILLED"); self.assertEqual(order.filled_quantity, Decimal("10"))
        self.assertEqual(list(SimulatedTrade.objects.filter(order=order).values_list("quantity", flat=True)), [Decimal("4"), Decimal("6")])
        self.assertEqual(SimulatedPosition.objects.get(instrument_id="BTC-USD").quantity, Decimal("10"))
        self.assertEqual(order.average_fill_price, Decimal("100"))

    def test_non_marketable_limits_remain_open(self):
        provider = SimulatedExecutionProvider("IMMEDIATE_FULL_FILL")
        buy = SimpleNamespace(id=uuid.uuid4(), instrument_id="BTC-USD", order_type="LIMIT", side="BUY", limit_price=Decimal("99"), quantity=Decimal("1"))
        sell = SimpleNamespace(id=uuid.uuid4(), instrument_id="BTC-USD", order_type="LIMIT", side="SELL", limit_price=Decimal("101"), quantity=Decimal("1"))
        marketable_buy = SimpleNamespace(id=uuid.uuid4(), instrument_id="BTC-USD", order_type="LIMIT", side="BUY", limit_price=Decimal("100"), quantity=Decimal("1"))

        self.assertEqual(provider.submit_order(buy), [])
        self.assertEqual(provider.submit_order(sell), [])
        self.assertEqual(provider.submit_order(marketable_buy)[0].price, Decimal("100.00"))

    def test_position_increase_partial_reduction_and_full_close(self):
        first = TradingOrder.objects.get(pk=self.post_order({**self.payload, "quantity": "4"}, key="position-open").json()["id"])
        process_created_order(first.id, "IMMEDIATE_FULL_FILL")
        second = TradingOrder.objects.get(pk=self.post_order({**self.payload, "quantity": "6"}, key="position-increase").json()["id"])
        process_created_order(second.id, "IMMEDIATE_FULL_FILL")
        partial = TradingOrder.objects.get(pk=self.post_order({**self.payload, "side": "SELL", "quantity": "4"}, key="position-reduce").json()["id"])
        process_created_order(partial.id, "IMMEDIATE_FULL_FILL")
        self.assertEqual(SimulatedPosition.objects.get(instrument_id="BTC-USD").quantity, Decimal("6"))
        close = TradingOrder.objects.get(pk=self.post_order({**self.payload, "side": "SELL", "quantity": "6"}, key="position-close").json()["id"])
        process_created_order(close.id, "IMMEDIATE_FULL_FILL")
        position = SimulatedPosition.objects.get(instrument_id="BTC-USD")
        self.assertEqual(position.quantity, Decimal("0"))
        self.assertEqual(position.average_price, Decimal("0"))

    def test_duplicate_execution_has_zero_duplicate_trade_or_settlement_effects(self):
        order = TradingOrder.objects.get(pk=self.post_order().json()["id"])
        process_created_order(order.id, "OPEN_THEN_CANCEL")
        execution = SimulatedExecution(f"sim:{order.id}:dedupe", Decimal("10"), Decimal("100"), True)
        self.assertTrue(apply_execution(order.id, execution)); self.assertFalse(apply_execution(order.id, execution))
        self.assertEqual(SimulatedTrade.objects.filter(execution_id=execution.execution_id).count(), 1)
        self.assertEqual(ProcessedEvent.objects.filter(consumer_name="simulated-execution-v1").count(), 1)
        self.assertEqual(SimulatedPosition.objects.get(instrument_id="BTC-USD").quantity, Decimal("10"))

    def test_open_then_cancel_releases_reservation(self):
        order = TradingOrder.objects.get(pk=self.post_order().json()["id"]); process_created_order(order.id, "OPEN_THEN_CANCEL")
        response = self.client.post(f"/api/v1/trading/orders/{order.id}/cancel", {}, format="json", **self.headers)
        self.assertEqual(response.status_code, 200); self.assertEqual(response.json()["state"], "CANCELLED")
        self.assertEqual(SimulatedReservation.objects.get(order_id=order.id).state, "RELEASED")

    def test_reject_and_expire_are_deterministic_and_release_funds(self):
        rejected = TradingOrder.objects.get(pk=self.post_order(key="reject").json()["id"]); process_created_order(rejected.id, "REJECT"); rejected.refresh_from_db()
        expired = TradingOrder.objects.get(pk=self.post_order(key="expire").json()["id"]); process_created_order(expired.id, "EXPIRE"); expired.refresh_from_db()
        self.assertEqual((rejected.state, expired.state), ("REJECTED", "EXPIRED"))
        self.assertEqual(SimulatedReservation.objects.filter(order_id__in=(rejected.id, expired.id), state="RELEASED").count(), 2)

    def test_stale_market_and_halt_deny_without_reservation_or_execution(self):
        with override_settings(SIMULATED_MARKET_DATA_STALE=True):
            stale = self.client.post("/api/v1/trading/orders/preview", self.payload, format="json", **self.headers)
        self.assertEqual(stale.json()["decision"], "DENY"); self.assertIn("MARKET_DATA_STALE", stale.json()["reason_codes"])
        TradingControl.objects.create(scope="PLATFORM", scope_ref="*", state="HALTED", reason="test", request_id="test", changed_by_ref="test")
        halted = self.client.post("/api/v1/trading/orders/preview", self.payload, format="json", **self.headers)
        self.assertEqual(halted.json()["decision"], "DENY"); self.assertIn("TRADING_HALTED", halted.json()["reason_codes"])
        TradingControl.objects.all().delete()
        with override_settings(SIMULATED_MARKET_DATA_STALE=True):
            stale_create = self.post_order(self.payload)
        self.assertEqual(stale_create.status_code, 409)
        self.assertEqual(stale_create.json()["error"]["code"], "MARKET_DATA_STALE")
        self.assertEqual(SimulatedReservation.objects.count(), 0); self.assertEqual(SimulatedTrade.objects.count(), 0)

    def test_trading_controls_apply_to_simulation(self):
        expected = {
            "ACTIVE": "ALLOW",
            "CLOSE_ONLY": "DENY",
            "CANCEL_ONLY": "DENY",
            "HALTED": "DENY",
            "MAINTENANCE": "DENY",
        }
        for state, decision in expected.items():
            TradingControl.objects.all().delete()
            TradingControl.objects.create(
                scope="PLATFORM",
                scope_ref="*",
                state=state,
                reason="simulation control test",
                request_id=f"control-{state}",
                changed_by_ref="test",
            )
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                self.payload,
                format="json",
                **self.headers,
            )
            self.assertEqual(response.json()["decision"], decision, state)

    def test_same_idempotency_key_creates_one_order_and_reservation(self):
        first = self.post_order(key="same-key"); second = self.post_order(key="same-key")
        self.assertEqual(first.json(), second.json()); self.assertEqual(TradingOrder.objects.count(), 1); self.assertEqual(SimulatedReservation.objects.count(), 1)

    def test_cross_tenant_and_user_access_is_zero(self):
        order_id = self.post_order().json()["id"]
        other = User.objects.create_user(email=f"other-{uuid.uuid4()}@example.invalid", phone_number=f"+1312{uuid.uuid4().int % 10000000:07d}", password="test")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"/api/v1/trading/orders/{order_id}", **self.headers).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/trading/orders/{order_id}/cancel", {}, format="json", **self.headers).status_code, 404)

    def test_balance_never_overspends_and_sell_beyond_position_is_denied(self):
        too_large = self.client.post("/api/v1/trading/orders/preview", {**self.payload, "quantity": "101"}, format="json", **self.headers)
        self.assertEqual(too_large.json()["decision"], "DENY"); self.assertIn("INSUFFICIENT_AVAILABLE_BALANCE", too_large.json()["reason_codes"])
        sell = self.post_order({**self.payload, "side": "SELL", "quantity": "1"})
        self.assertEqual(sell.status_code, 409); self.assertEqual(TradingOrder.objects.count(), 0)

    def test_portfolio_is_canonical_and_simulation_only(self):
        response = self.client.get("/api/v1/trading/portfolio", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["simulation"])
        self.assertIsNone(response.json()["margin_if_applicable"])

    def test_replace_fails_closed_until_provider_capability_is_certified(self):
        order_id = self.post_order().json()["id"]
        response = self.client.post(f"/api/v1/trading/orders/{order_id}/replace", {"quantity": "2"}, format="json", **self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "CAPABILITY_UNSUPPORTED")


class CompleteTransitionMatrixTests(TestCase):
    def test_every_state_pair_matches_the_declared_matrix(self):
        for current in OrderState:
            for target in OrderState:
                allowed = target in TRANSITIONS.get(current, set())
                if allowed: self.assertEqual(transition_order(current, target), target)
                else:
                    with self.assertRaises(InvalidOrderTransition): transition_order(current, target)

    @override_settings(SIMULATED_TRADING_REQUESTED=True, DEPLOYMENT_ENV="production")
    def test_production_rejects_attempted_simulation_enablement(self):
        self.assertIn("codestra.E004", {error.id for error in financial_database_isolation()})


@SIMULATION
class SimulatedOrderConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_20_duplicate_order_requests_create_one_order_and_reservation(self):
        user = User.objects.create_user(
            email=f"sim-concurrent-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1415{uuid.uuid4().int % 10000000:07d}",
            password="test",
        )
        approve_for_simulation(user, "Concurrent Simulation Test")
        barrier = threading.Barrier(20)
        payload = {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "1"}

        def submit(_index):
            close_old_connections()
            barrier.wait()
            caller = User.objects.get(pk=user.pk)
            body, status = create(caller, payload, "one-logical-order")
            close_old_connections()
            return body["id"], status

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(submit, range(20)))
        self.assertEqual({status for _, status in results}, {200, 201})
        self.assertEqual(len({order_id for order_id, _ in results}), 1)
        self.assertEqual(TradingOrder.objects.count(), 1)
        self.assertEqual(SimulatedReservation.objects.count(), 1)

    def test_concurrent_cancel_and_fill_has_one_consistent_outcome(self):
        user = User.objects.create_user(
            email=f"sim-race-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1617{uuid.uuid4().int % 10000000:07d}",
            password="test",
        )
        approve_for_simulation(user, "Race Simulation Test")
        body, _ = create(user, {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "1"}, "race-order")
        order = process_created_order(body["id"], "OPEN_THEN_CANCEL")
        barrier = threading.Barrier(2)

        def race(action):
            close_old_connections(); barrier.wait()
            try:
                if action == "cancel": cancel(User.objects.get(pk=user.pk), order.id)
                else: apply_execution(order.id, SimulatedExecution(f"sim:{order.id}:race", Decimal("1"), Decimal("100"), True))
            except (ValueError, InvalidOrderTransition):
                pass
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(race, ("cancel", "fill")))
        order.refresh_from_db()
        reservation = SimulatedReservation.objects.get(order_id=order.id)
        if order.state == "FILLED":
            self.assertEqual(SimulatedTrade.objects.filter(order=order).count(), 1)
            self.assertEqual(reservation.state, "CONSUMED")
        else:
            self.assertEqual(order.state, "CANCELLED")
            self.assertEqual(SimulatedTrade.objects.filter(order=order).count(), 0)
            self.assertEqual(reservation.state, "RELEASED")
