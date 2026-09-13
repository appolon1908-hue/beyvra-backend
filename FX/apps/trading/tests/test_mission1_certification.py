"""Mission 1 certification regressions for canonical PAPER trading.

These tests intentionally exercise the public contract against PostgreSQL.
They are not substitutes for the external certification run, but they prevent
the failures found on the stale candidate from returning unnoticed.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.compliance.domain import (
    AccountState,
    AmlState,
    JurisdictionState,
    KycState,
    SanctionsState,
)
from apps.compliance.models import ComplianceProfile
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent
from apps.post_trade.models import Trade
from apps.trading.application.context import TradingContext
from apps.trading.application.simulation import (
    account_for,
    cancel,
    create,
    position_order,
    process_created_order,
    replace,
)
from apps.trading.models import (
    ExecutionProviderRecord,
    SimulatedPosition,
    SimulatedReservation,
    TradingOrder,
)
from integrations.models import Organization, OrganizationMembership
from reference_data.models import Instrument, InstrumentVersion
from reference_data.services import record_market_observation
from users.models import User
from ws.v2 import _owns_demo_account

from .fixtures import ensure_paper_settlement_calendar


MISSION1_SETTINGS = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    SIMULATED_EXECUTION_INLINE=False,
    REAL_TRADING_ENABLED=False,
    REAL_MONEY_ENABLED=False,
    REAL_SETTLEMENT_ENABLED=False,
    REAL_MARGIN_ENABLED=False,
    REAL_LIQUIDATION_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    LIVE_BROKER_ROUTING_ENABLED=False,
    FIX_LIVE_SESSION_ENABLED=False,
)


def create_user(label):
    return User.objects.create_user(
        email=f"{label}-{uuid.uuid4()}@example.invalid",
        phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
        password="test-only-password",
    )


def add_membership(user, label, *, verified):
    organization = Organization.objects.create(name=f"{label} {uuid.uuid4()}")
    OrganizationMembership.objects.create(user=user, organization=organization)
    profile = ComplianceProfile.objects.create(user=user, organization=organization)
    if verified:
        profile.account_state = AccountState.ACTIVE
        profile.kyc_state = KycState.APPROVED
        profile.aml_state = AmlState.CLEARED
        profile.sanctions_state = SanctionsState.CLEAR
        profile.jurisdiction_state = JurisdictionState.SUPPORTED
        profile.save()
    return organization


@MISSION1_SETTINGS
class Mission1AuthorityAndIsolationTests(TestCase):
    def setUp(self):
        ensure_paper_settlement_calendar()
        self.instrument = Instrument.objects.get(canonical_symbol="BTC-USD", venue=None)
        self.user = create_user("mission1")
        self.tenant_a = add_membership(self.user, "Tenant A", verified=True)
        self.tenant_b = add_membership(self.user, "Tenant B", verified=False)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.simulation = {"HTTP_X_BEYVRA_SIMULATION_MODE": "true"}
        self.payload = {
            "instrument": str(self.instrument.instrument_id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "1",
        }

    def headers(self, organization):
        return {
            **self.simulation,
            "HTTP_X_ORGANIZATION_ID": str(organization.id),
        }

    def post_order(self, organization, *, key=None, payload=None):
        return self.client.post(
            "/api/v1/trading/orders",
            payload or self.payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
            **self.headers(organization),
        )

    def test_tenant_resolution_and_account_identity_are_unambiguous(self):
        missing = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.simulation,
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"]["code"], "TENANT_SELECTION_REQUIRED")

        context_a = TradingContext.for_user(self.user, self.tenant_a.id)
        context_b = TradingContext.for_user(self.user, self.tenant_b.id)
        self.assertNotEqual(context_a.tenant_ref, context_b.tenant_ref)
        self.assertNotEqual(context_a.account_ref, context_b.account_ref)
        self.assertEqual(context_a.organization_id, self.tenant_a.id)
        self.assertEqual(context_a.user_id, self.user.id)

        foreign = Organization.objects.create(name="Foreign")
        response = self.client.get(
            "/api/v1/trading/orders",
            **self.headers(foreign),
        )
        self.assertEqual(response.status_code, 403)
        malformed = self.client.get(
            "/api/v1/trading/orders",
            **self.simulation,
            HTTP_X_ORGANIZATION_ID="not-a-uuid",
        )
        self.assertEqual(malformed.status_code, 403)

        OrganizationMembership.objects.filter(
            user=self.user,
            organization=self.tenant_a,
        ).update(is_active=False)
        inactive = self.client.get(
            "/api/v1/trading/orders",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(inactive.status_code, 403)

    def test_compliance_is_tenant_scoped_and_preview_create_share_authorities(self):
        preview = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.headers(self.tenant_a),
        )
        created = self.post_order(self.tenant_a, key="parity")
        self.assertEqual((preview.status_code, created.status_code), (200, 201))
        self.assertEqual(preview.json()["decision"], "ALLOW")
        self.assertEqual(preview.json()["tenant_ref"], created.json()["tenant_ref"])
        self.assertEqual(preview.json()["account_ref"], created.json()["account_ref"])
        self.assertEqual(preview.json()["instrument"], created.json()["instrument"])
        self.assertEqual(preview.json()["price"], created.json()["reference_price"])
        self.assertEqual(preview.json()["fees"]["total"], created.json()["fees"]["total"])
        self.assertEqual(
            preview.json()["fees"]["schedule_version"],
            created.json()["fees"]["schedule_version"],
        )

        denied = self.post_order(self.tenant_b, key="tenant-b-denied")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(TradingOrder.objects.filter(tenant_ref=str(self.tenant_b.id)).count(), 0)
        self.assertTrue(
            ApplicationAuditEvent.objects.filter(
                action="simulation.order.rejected",
                context__tenant_ref=str(self.tenant_b.id),
            ).exists()
        )

    def test_cross_tenant_resources_are_not_enumerable(self):
        created = self.post_order(self.tenant_a, key="tenant-a-order")
        self.assertEqual(created.status_code, 201)
        order = TradingOrder.objects.get(pk=created.json()["id"])
        process_created_order(order.id, "IMMEDIATE_FULL_FILL")
        position = SimulatedPosition.objects.get(account__tenant_ref=str(self.tenant_a.id))
        trade = Trade.objects.get(order_id=order.id)

        for path in (
            f"/api/v1/trading/orders/{order.id}",
            f"/api/v1/trading/trades/{trade.id}",
            f"/api/v1/trading/positions/{position.id}",
            f"/api/v1/execution/routes/{order.id}",
            f"/api/v1/execution/quality/{order.id}",
        ):
            self.assertEqual(self.client.get(path, **self.headers(self.tenant_b)).status_code, 404, path)

        order.refresh_from_db()
        cancel_response = self.client.post(
            f"/api/v1/trading/orders/{order.id}/cancel",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="foreign-cancel",
            HTTP_IF_MATCH=str(order.version),
            **self.headers(self.tenant_b),
        )
        self.assertEqual(cancel_response.status_code, 404)
        close_response = self.client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="foreign-close",
            **self.headers(self.tenant_b),
        )
        self.assertEqual(close_response.status_code, 404)

    @override_settings(SIMULATED_EXECUTION_PRICES={"BTC-USD": "999999"})
    def test_canonical_price_fee_and_side_economics_ignore_static_settings(self):
        buy = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.headers(self.tenant_a),
        )
        sell = self.client.post(
            "/api/v1/trading/orders/preview",
            {**self.payload, "side": "SELL"},
            format="json",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(buy.json()["price"], "100.00")
        self.assertEqual(sell.json()["price"], "99.00")
        evidence = buy.json()["price_evidence"]
        self.assertEqual(evidence["source"], "paper-market")
        self.assertEqual(evidence["provider_health"], "HEALTHY")
        self.assertTrue(evidence["observation_id"])
        self.assertTrue(evidence["observed_at"])
        self.assertTrue(evidence["stale_after"])
        self.assertEqual(buy.json()["fees"]["commission"], "0.10")
        self.assertEqual(buy.json()["fees"]["total"], "0.10")
        self.assertIn("PAPER-TRADING-COMMISSION-V1", buy.json()["fees"]["schedule_version"])

    def test_symbol_guessing_and_unsupported_order_types_fail_closed(self):
        for instrument in ("BTCUSD", "BTC_USD", "UNKNOWN"):
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                {**self.payload, "instrument": instrument},
                format="json",
                **self.headers(self.tenant_a),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "INSTRUMENT_UNAVAILABLE")
        for order_type in ("STOP", "STOP_LIMIT"):
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                {**self.payload, "order_type": order_type},
                format="json",
                **self.headers(self.tenant_a),
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "ORDER_TYPE_UNSUPPORTED")

    def test_price_freshness_validity_and_provider_health_fail_closed(self):
        now = timezone.now()
        record_market_observation(
            provider_id="paper-market",
            provider_symbol="BTC-USD",
            data_type="QUOTE",
            provider_event_id=f"stale-{uuid.uuid4()}",
            observed_at=now,
            payload_safe={
                "bid": "99",
                "ask": "100",
                "mid": "99.5",
                "stale_after": (now - timedelta(seconds=1)).isoformat(),
            },
        )
        stale = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(stale.status_code, 503)
        self.assertEqual(stale.json()["error"]["code"], "PRICE_STALE")

        missing_instrument = Instrument.objects.create(
            canonical_symbol="ETH-USD",
            name="Ethereum / US Dollar PAPER",
            asset_class=Instrument.AssetClass.CRYPTO,
            currency="USD",
            calendar=self.instrument.calendar,
            status=Instrument.Status.ACTIVE,
            tick_size="0.01",
            lot_size="0.0001",
        )
        source_version = self.instrument.versions.get(version=1)
        InstrumentVersion.objects.create(
            instrument=missing_instrument,
            version=1,
            canonical_symbol=missing_instrument.canonical_symbol,
            name=missing_instrument.name,
            status=Instrument.Status.ACTIVE,
            tick_size=source_version.tick_size,
            lot_size=source_version.lot_size,
            metadata=source_version.metadata,
            effective_from=timezone.now() - timedelta(days=1),
        )
        missing = self.client.post(
            "/api/v1/trading/orders/preview",
            {**self.payload, "instrument": str(missing_instrument.instrument_id)},
            format="json",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(missing.status_code, 503)
        self.assertEqual(missing.json()["error"]["code"], "PRICE_UNAVAILABLE")

        ensure_paper_settlement_calendar()
        ExecutionProviderRecord.objects.filter(provider_id="paper-market").update(health="DEGRADED")
        unhealthy = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(unhealthy.status_code, 503)
        self.assertEqual(unhealthy.json()["error"]["code"], "PROVIDER_UNAVAILABLE")

    def test_invalid_financial_numbers_never_raise_http_500(self):
        invalid_quantities = (
            "NaN",
            "Infinity",
            "-Infinity",
            "-1",
            "0",
            "1e999",
            "9999999999999999999999999999999999999",
            "0.0000000000000000001",
        )
        for quantity in invalid_quantities:
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                {**self.payload, "quantity": quantity},
                format="json",
                HTTP_X_REQUEST_ID="numeric-regression",
                HTTP_X_CORRELATION_ID="numeric-correlation",
                **self.headers(self.tenant_a),
            )
            self.assertEqual(response.status_code, 422, quantity)
            self.assertIn(response.json()["error"]["code"], {"INVALID_QUANTITY", "INVALID_QUANTITY_PRECISION"})
            self.assertEqual(response.json()["error"]["request_id"], "numeric-regression")
            self.assertEqual(response.json()["error"]["correlation_id"], "numeric-correlation")

        for price in ("NaN", "Infinity", "-Infinity", "1e999", "1.0000000000000000001"):
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                {**self.payload, "order_type": "LIMIT", "limit_price": price},
                format="json",
                **self.headers(self.tenant_a),
            )
            self.assertEqual(response.status_code, 422, price)
            self.assertIn(response.json()["error"]["code"], {"INVALID_PRICE", "INVALID_PRICE_PRECISION"})

    def test_instrument_boundaries_tick_lot_and_market_state(self):
        cases = (
            ({**self.payload, "quantity": "0.00001"}, "MIN_QUANTITY_NOT_MET"),
            ({**self.payload, "quantity": "0.00015"}, "INVALID_LOT_SIZE"),
            ({**self.payload, "quantity": "100.0001"}, "MAX_QUANTITY_EXCEEDED"),
            ({**self.payload, "order_type": "LIMIT", "limit_price": "99.999"}, "INVALID_TICK_SIZE"),
        )
        for payload, code in cases:
            response = self.client.post(
                "/api/v1/trading/orders/preview",
                payload,
                format="json",
                **self.headers(self.tenant_a),
            )
            self.assertEqual(response.status_code, 422, code)
            self.assertEqual(response.json()["error"]["code"], code)

        self.instrument.status = Instrument.Status.HALTED
        self.instrument.save(update_fields=("status",))
        halted = self.client.post(
            "/api/v1/trading/orders/preview",
            self.payload,
            format="json",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(halted.status_code, 422)
        self.assertEqual(halted.json()["error"]["code"], "INSTRUMENT_UNAVAILABLE")

    def test_create_and_replace_idempotency_and_version_contract(self):
        first = self.post_order(self.tenant_a, key="create-replay")
        replay = self.post_order(self.tenant_a, key="create-replay")
        self.assertEqual((first.status_code, replay.status_code), (201, 201))
        self.assertEqual(first.json(), replay.json())
        conflict = self.post_order(
            self.tenant_a,
            key="create-replay",
            payload={**self.payload, "quantity": "2"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

        limit = self.post_order(
            self.tenant_a,
            key="replace-source",
            payload={**self.payload, "order_type": "LIMIT", "limit_price": "99"},
        )
        order = process_created_order(limit.json()["id"], "OPEN_THEN_CANCEL")
        original_version = order.version
        replaced = self.client.post(
            f"/api/v1/trading/orders/{order.id}/replace",
            {"limit_price": "98"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="replace-replay",
            HTTP_IF_MATCH=str(original_version),
            **self.headers(self.tenant_a),
        )
        replayed = self.client.post(
            f"/api/v1/trading/orders/{order.id}/replace",
            {"limit_price": "98"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="replace-replay",
            HTTP_IF_MATCH=str(original_version),
            **self.headers(self.tenant_a),
        )
        self.assertEqual((replaced.status_code, replayed.status_code), (200, 200))
        self.assertEqual(replaced.json(), replayed.json())
        order.refresh_from_db()
        increase = self.client.post(
            f"/api/v1/trading/orders/{order.id}/replace",
            {"limit_price": "100"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="replace-increase",
            HTTP_IF_MATCH=str(order.version),
            **self.headers(self.tenant_a),
        )
        self.assertEqual(increase.status_code, 409)
        self.assertEqual(increase.json()["error"]["code"], "RESERVATION_INCREASE_REQUIRED")

    def test_position_detail_reduce_and_close_use_sell_market_orders(self):
        opened = self.post_order(
            self.tenant_a,
            key="position-open",
            payload={**self.payload, "quantity": "3"},
        )
        process_created_order(opened.json()["id"], "IMMEDIATE_FULL_FILL")
        position = SimulatedPosition.objects.get(account__tenant_ref=str(self.tenant_a.id))
        detail = self.client.get(
            f"/api/v1/trading/positions/{position.id}",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["quantity"], "3.000000000000000000")

        reduced = self.client.post(
            f"/api/v1/trading/positions/{position.id}/reduce",
            {"quantity": "1"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="position-reduce",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(reduced.status_code, 201)
        self.assertEqual((reduced.json()["side"], reduced.json()["order_type"]), ("SELL", "MARKET"))
        process_created_order(reduced.json()["id"], "IMMEDIATE_FULL_FILL")

        closed = self.client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="position-close",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(closed.status_code, 201)
        self.assertEqual(Decimal(closed.json()["quantity"]), Decimal("2"))
        self.assertEqual((closed.json()["side"], closed.json()["order_type"]), ("SELL", "MARKET"))
        self.assertTrue(
            OutboxEvent.objects.filter(
                event_type="trading.position.close_requested.v1",
                tenant_ref=str(self.tenant_a.id),
                payload__account_ref=TradingContext.for_user(self.user, self.tenant_a.id).account_ref,
            ).exists()
        )
        process_created_order(closed.json()["id"], "IMMEDIATE_FULL_FILL")
        position.refresh_from_db()
        self.assertEqual(position.quantity, Decimal("0"))
        replay = self.client.post(
            f"/api/v1/trading/positions/{position.id}/close",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="position-close",
            **self.headers(self.tenant_a),
        )
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), closed.json())
        self.assertEqual(
            OutboxEvent.objects.filter(
                event_type="trading.position.close_requested.v1",
                aggregate_id=str(position.id),
            ).count(),
            1,
        )

    def test_realtime_account_authorization_includes_tenant_identity(self):
        context_a = TradingContext.for_user(self.user, self.tenant_a.id)
        context_b = TradingContext.for_user(self.user, self.tenant_b.id)
        channel_a = f"simulation.order.{context_a.account_ref}"
        self.assertTrue(_owns_demo_account(self.user.id, channel_a, str(self.tenant_a.id)))
        self.assertFalse(_owns_demo_account(self.user.id, channel_a, str(self.tenant_b.id)))
        self.assertNotEqual(context_a.account_ref, context_b.account_ref)

    def test_live_and_real_capabilities_remain_disabled(self):
        for name in (
            "REAL_TRADING_ENABLED",
            "REAL_MONEY_ENABLED",
            "REAL_SETTLEMENT_ENABLED",
            "REAL_MARGIN_ENABLED",
            "REAL_LIQUIDATION_ENABLED",
            "EXTERNAL_EXECUTION_ENABLED",
            "LIVE_BROKER_ROUTING_ENABLED",
            "FIX_LIVE_SESSION_ENABLED",
        ):
            self.assertFalse(getattr(settings, name, False), name)
        response = self.client.get(
            "/api/v1/execution/capabilities",
            **self.headers(self.tenant_a),
        )
        capabilities = response.json()["paper_capabilities"]
        self.assertTrue(all(capabilities[name] for name in ("MARKET", "LIMIT", "CANCEL", "REPLACE", "POSITION_CLOSE", "POSITION_REDUCE")))
        self.assertFalse(capabilities["STOP"])
        self.assertFalse(capabilities["STOP_LIMIT"])
        self.assertFalse(response.json()["external_execution_enabled"])
        self.assertFalse(response.json()["real_trading_enabled"])

    def test_postgresql_constraints_enforce_long_only_and_decimal_ranges(self):
        context = TradingContext.for_user(self.user, self.tenant_a.id)
        account = account_for(context)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SimulatedPosition.objects.create(
                account=account,
                instrument_id=str(self.instrument.instrument_id),
                quantity=Decimal("-0.0001"),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            TradingOrder.objects.create(
                tenant_ref=context.tenant_ref,
                subject_ref=context.subject_ref,
                account_ref=context.account_ref,
                instrument_id=str(self.instrument.instrument_id),
                order_type="MARKET",
                side="BUY",
                quantity=Decimal("0"),
            )


@MISSION1_SETTINGS
class Mission1ConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        ensure_paper_settlement_calendar()
        self.instrument = Instrument.objects.get(canonical_symbol="BTC-USD", venue=None)
        self.user = create_user("mission1-race")
        self.organization = add_membership(self.user, "Race Tenant", verified=True)
        self.context = TradingContext.for_user(self.user, self.organization.id)
        opened, _ = create(
            self.context,
            {
                "instrument": str(self.instrument.instrument_id),
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "2",
            },
            "race-position-open",
        )
        process_created_order(opened["id"], "IMMEDIATE_FULL_FILL")

    def test_two_simultaneous_closes_cannot_over_reduce(self):
        position = SimulatedPosition.objects.get(account__tenant_ref=str(self.organization.id))
        barrier = threading.Barrier(2)

        def close_position(index):
            close_old_connections()
            try:
                caller = User.objects.get(pk=self.user.pk)
                context = TradingContext.for_user(caller, self.organization.id)
                barrier.wait()
                body, status = position_order(
                    context,
                    position.id,
                    command="close",
                    idempotency_key=f"concurrent-close-{index}",
                )
                return body["id"], status
            except ValueError as error:
                return str(error), 409
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(close_position, range(2)))
        self.assertEqual(sum(status == 201 for _, status in results), 1)
        self.assertEqual(
            TradingOrder.objects.filter(
                account_ref=self.context.account_ref,
                side="SELL",
            ).count(),
            1,
        )
        self.assertEqual(
            SimulatedReservation.objects.filter(
                account__account_ref=self.context.account_ref,
                state="ACTIVE",
                asset=str(self.instrument.instrument_id),
            ).count(),
            1,
        )

    def test_replace_cancel_race_has_one_legal_economic_result(self):
        body, _ = create(
            self.context,
            {
                "instrument": str(self.instrument.instrument_id),
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": "1",
                "limit_price": "99",
            },
            "race-limit",
        )
        order = process_created_order(body["id"], "OPEN_THEN_CANCEL")
        expected_version = order.version
        barrier = threading.Barrier(2)

        def mutate(action):
            close_old_connections()
            caller = User.objects.get(pk=self.user.pk)
            context = TradingContext.for_user(caller, self.organization.id)
            try:
                barrier.wait()
                if action == "cancel":
                    cancel(context, order.id, "race-cancel", expected_version)
                else:
                    replace(
                        context,
                        order.id,
                        {"limit_price": "98"},
                        "race-replace",
                        expected_version,
                    )
                return "success"
            except ValueError as error:
                return str(error)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mutate, ("cancel", "replace")))
        self.assertEqual(results.count("success"), 1)
        order.refresh_from_db()
        reservation = SimulatedReservation.objects.get(order_id=order.id)
        if order.state == "CANCELLED":
            self.assertEqual(reservation.state, "RELEASED")
        else:
            self.assertEqual(order.state, "OPEN")
            self.assertEqual(order.limit_price, Decimal("98"))
            self.assertEqual(reservation.state, "ACTIVE")
        emitted = OutboxEvent.objects.filter(
            aggregate_id=str(order.id),
            event_type__in=("trading.order.cancelled.v1", "trading.order.replaced.v1"),
        ).count()
        self.assertEqual(emitted, 1)
