import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.foundation.models import OutboxEvent
from apps.post_trade.allocation import TradeAllocationService
from apps.post_trade.calendar import SettlementCalendarService
from apps.post_trade.corrections import TradeCorrectionService
from apps.post_trade.models import PostTradeAudit, PostTradeException, SettlementInstruction, Trade, TradeAllocation, TradeConfirmation, TradePositionEffect
from apps.post_trade.processor import process_simulated_fill
from apps.post_trade.reconciliation import PositionReconciler
from apps.post_trade.state import PostTradeStateService
from apps.trading.application.simulation import create, process_created_order
from apps.trading.models import SimulatedReservation, TradingOrder
from users.models import User


@override_settings(SIMULATED_TRADING_ENABLED=True, DEPLOYMENT_ENV="test", SIMULATED_EXECUTION_INLINE=False, SURVEILLANCE_ENABLED=True, SELF_TRADE_PREVENTION_ENABLED=True)
class PostTradeAuthorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="post-trade@example.test", password="safe-password", phone_number="+15550001001")
        self.other = User.objects.create_user(email="other-post-trade@example.test", password="safe-password", phone_number="+15550001002")
        self.manager = User.objects.create_user(email="post-trade-manager@example.test", password="safe-password", phone_number="+15550001003")
        Group.objects.get_or_create(name="post_trade_manager")[0].user_set.add(self.manager)

    def filled_trade(self, key="post-trade-order"):
        body, _ = create(self.user, {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "0.01"}, key)
        order = process_created_order(body["id"], scenario="IMMEDIATE_FULL_FILL")
        return order, Trade.objects.get(order_id=order.id)

    def test_complete_trace_and_reconciliation(self):
        order, trade = self.filled_trade()
        self.assertEqual(trade.allocations.count(), 1)
        self.assertEqual(trade.obligations.count(), 3)
        self.assertEqual(trade.position_effects.count(), 1)
        self.assertEqual(trade.confirmations.count(), 1)
        self.assertTrue(hasattr(trade, "settlement_instruction"))
        self.assertEqual(SimulatedReservation.objects.get(order_id=order.id).state, "CONSUMED")
        self.assertEqual(PositionReconciler.run(persist=False)["status"], "PASS")
        self.assertTrue(OutboxEvent.objects.filter(aggregate_id=str(trade.id), event_type="trade.captured.v1").exists())

    def test_duplicate_fill_creates_one_business_chain(self):
        order, trade = self.filled_trade("duplicate-chain")
        legacy = order.simulated_trades.get()
        for _ in range(100):
            duplicate, created = process_simulated_fill(order=order, execution_id=legacy.execution_id, quantity=legacy.quantity, price=legacy.price, fee=legacy.fee, executed_at=legacy.executed_at)
            self.assertFalse(created); self.assertEqual(duplicate.id, trade.id)
        self.assertEqual(Trade.objects.filter(execution_id=legacy.execution_id).count(), 1)
        self.assertEqual(SettlementInstruction.objects.filter(trade=trade).count(), 1)
        self.assertEqual(TradePositionEffect.objects.filter(trade=trade, effect_type="TRADE").count(), 1)

    def test_partial_fills_preserve_each_fill_and_do_not_overfill(self):
        body, _ = create(self.user, {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "0.01"}, "partial-fill")
        order = process_created_order(body["id"], scenario="PARTIAL_THEN_FILL")
        trades = Trade.objects.filter(order_id=order.id)
        self.assertEqual(trades.count(), 2)
        self.assertEqual(sum((row.quantity for row in trades), Decimal("0")), order.quantity)
        self.assertEqual(order.filled_quantity, order.quantity)
        self.assertEqual(PositionReconciler.run(persist=False)["status"], "PASS")

    def test_sell_obligations_are_asset_delivery_and_cash_credit(self):
        self.filled_trade("buy-before-sell")
        body, _ = create(self.user, {"instrument": "BTC-USD", "side": "SELL", "order_type": "MARKET", "quantity": "0.005"}, "sell")
        order = process_created_order(body["id"], scenario="IMMEDIATE_FULL_FILL")
        trade = Trade.objects.get(order_id=order.id)
        self.assertTrue(trade.obligations.filter(obligation_type="ASSET_DELIVERY", quantity=Decimal("0.005")).exists())
        self.assertTrue(trade.obligations.filter(obligation_type="CASH_CREDIT").exists())

    def test_allocation_invariants(self):
        _, trade = self.filled_trade("allocation")
        self.assertTrue(TradeAllocationService.validate(trade))
        TradeAllocation.objects.filter(trade=trade).update(allocation_quantity=trade.quantity / 2)
        with self.assertRaisesRegex(ValueError, "ALLOCATION_QUANTITY_MISMATCH"): TradeAllocationService.validate(trade)
        with self.assertRaisesRegex(ValueError, "ALLOCATION_QUANTITY_MISMATCH"): TradeAllocationService.allocate(trade, [{"account_ref": trade.account_ref, "quantity": trade.quantity * 2}])

    def test_state_machine_rejects_terminal_regression(self):
        _, trade = self.filled_trade("state")
        trade.trade_state = "SETTLED"; trade.save(update_fields=("trade_state", "updated_at"))
        self.assertFalse(PostTradeStateService.can_transition("SETTLED", "SETTLEMENT_PENDING"))
        with self.assertRaisesRegex(ValueError, "INVALID_POST_TRADE_TRANSITION"): PostTradeStateService.transition(trade, "SETTLEMENT_PENDING")

    def test_obligations_decimal_and_confirmation_snapshot(self):
        _, trade = self.filled_trade("evidence")
        cash = trade.obligations.get(obligation_type="CASH_DEBIT")
        self.assertIsInstance(cash.amount, Decimal)
        confirmation = trade.confirmations.get()
        original = confirmation.instrument_snapshot.copy()
        TradingOrder.objects.filter(pk=trade.order_id).update(instrument_id="RENAMED-SYMBOL")
        confirmation.refresh_from_db(); self.assertEqual(confirmation.instrument_snapshot, original)
        with self.assertRaises(DatabaseError), transaction.atomic(): TradeConfirmation.objects.filter(pk=confirmation.pk).update(instrument_snapshot={"tampered": True})
        with self.assertRaises(DatabaseError), transaction.atomic(): TradePositionEffect.objects.filter(trade=trade).update(quantity_delta=Decimal("999"))

    def test_calendar_weekend_holiday_and_crypto_policy(self):
        settled, policy = SettlementCalendarService.calculate_settlement_date(trade_date=date(2026, 8, 8), asset_class="CRYPTO")
        self.assertEqual(settled, date(2026, 8, 8)); self.assertEqual(policy.settlement_convention, "INSTANT")

    def test_correction_requires_independent_approval_and_preserves_trade(self):
        _, trade = self.filled_trade("correction")
        correction = TradeCorrectionService.request(trade=trade, correction_type="REVERSAL", reason_code="SYNTHETIC_CORRECTION", actor_ref="maker")
        with self.assertRaisesRegex(ValueError, "SELF_APPROVAL_FORBIDDEN"): TradeCorrectionService.approve(correction, actor_ref="maker")
        TradeCorrectionService.approve(correction, actor_ref="checker")
        trade.refresh_from_db(); self.assertEqual(trade.trade_state, "REVERSED")
        self.assertEqual(trade.position_effects.count(), 2)
        self.assertTrue(Trade.objects.filter(pk=trade.pk).exists())

    def test_customer_tenant_scope_and_operator_rbac(self):
        _, trade = self.filled_trade("api")
        confirmation = trade.confirmations.get()
        owner = APIClient(); owner.force_authenticate(self.user)
        self.assertEqual(owner.get(f"/api/v1/post-trade/confirmations/{confirmation.id}").status_code, 200)
        self.assertEqual(owner.get(f"/api/v1/trading/trades/{trade.id}", HTTP_X_BEYVRA_SIMULATION_MODE="true").status_code, 200)
        other = APIClient(); other.force_authenticate(self.other)
        self.assertEqual(other.get(f"/api/v1/post-trade/confirmations/{confirmation.id}").status_code, 404)
        self.assertEqual(other.get("/api/v1/operator/post-trade/trades").status_code, 403)
        operator = APIClient(); operator.force_authenticate(self.manager)
        self.assertEqual(operator.get(f"/api/v1/operator/post-trade/trades/{trade.id}/evidence").status_code, 200)

    def test_critical_exception_maker_checker(self):
        _, trade = self.filled_trade("exception")
        row = PostTradeException.objects.create(tenant_ref="default", account_ref=trade.account_ref, trade=trade, exception_type="POSITION_MISMATCH", severity="CRITICAL", state="OPEN", detected_at=timezone.now(), requested_by="maker", evidence_hash="0" * 64)
        from apps.post_trade.exceptions import PostTradeExceptionService
        with self.assertRaisesRegex(ValueError, "SELF_APPROVAL_FORBIDDEN"): PostTradeExceptionService.resolve(row, actor_ref="maker", resolution_code="FIXTURE")
        PostTradeExceptionService.resolve(row, actor_ref="checker", resolution_code="FIXTURE")
        row.refresh_from_db(); self.assertEqual(row.state, "RESOLVED")

    def test_rejected_order_has_no_post_trade_effect(self):
        with self.assertRaises(ValueError): create(self.user, {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "999"}, "rejected")
        self.assertEqual(Trade.objects.count(), 0); self.assertEqual(SettlementInstruction.objects.count(), 0)

    def test_audit_is_database_append_only(self):
        _, trade = self.filled_trade("audit")
        row = PostTradeAudit.objects.filter(resource_ref=str(trade.id)).first()
        with self.assertRaises(DatabaseError), transaction.atomic(): PostTradeAudit.objects.filter(pk=row.pk).update(reason="tampered")
