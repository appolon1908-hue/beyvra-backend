import copy
from django.test import SimpleTestCase, TestCase, override_settings
from apps.trading.reconciliation import evaluate_snapshot, run
from apps.trading.application.simulation import create, process_created_order
from apps.trading.models import ReconciliationRun
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent
from users.models import User

def valid_snapshot():
    return {"orders":[{"id":"o1","quantity":"10","filled_quantity":"10","state":"FILLED","account_id":"a1"}],
      "trades":[{"execution_id":"e1","order_id":"o1","instrument_id":"BTC-USD","side":"BUY","quantity":"10"}],
      "reservations":[{"order_id":"o1","state":"CONSUMED","remaining_amount":"0"}],
      "positions":[{"account_id":"a1","instrument_id":"BTC-USD","quantity":"10"}],
      "accounts":[{"id":"a1","total_balance":"8999","pending_balance":"0"}],
      "outbox_order_ids":["o1"],"execution_outbox_ids":["e1"],"audit_order_ids":["o1"],"duplicate_trades":[],"duplicate_settlements":[],"duplicate_processed":[]}

class ReconciliationDetectionTests(SimpleTestCase):
    def codes(self,snapshot): return {v["check_code"] for v in evaluate_snapshot(snapshot)[1]}
    def test_valid_state_passes(self): self.assertEqual(self.codes(valid_snapshot()),set())
    def test_duplicate_trade_detected(self):
        data=valid_snapshot(); data["duplicate_trades"]=[{"execution_id":"e1","count":2}]; self.assertIn("DUPLICATE_TRADE",self.codes(data))
    def test_overfill_detected(self):
        data=valid_snapshot(); data["orders"][0]["quantity"]="9"; self.assertIn("OVERFILL",self.codes(data))
    def test_reservation_leak_detected(self):
        data=valid_snapshot(); data["reservations"][0].update(state="ACTIVE",remaining_amount="1"); self.assertIn("RESERVATION_LEAK",self.codes(data))
    def test_position_mismatch_detected(self):
        data=valid_snapshot(); data["positions"][0]["quantity"]="9"; self.assertIn("POSITION_MISMATCH",self.codes(data))
    def test_missing_outbox_detected(self):
        data=valid_snapshot(); data["outbox_order_ids"]=[]; self.assertIn("MISSING_REQUIRED_OUTBOX",self.codes(data))
    def test_audit_gap_detected(self):
        data=valid_snapshot(); data["audit_order_ids"]=[]; self.assertIn("AUDIT_GAP",self.codes(data))
    def test_missing_execution_event_detected(self):
        data=valid_snapshot(); data["execution_outbox_ids"]=[]; self.assertIn("MISSING_EXECUTION_EVENT",self.codes(data))
    def test_output_contains_only_opaque_entity_references(self):
        data=valid_snapshot(); data["audit_order_ids"]=[]; violation=evaluate_snapshot(data)[1][0]
        self.assertNotEqual(violation["opaque_entity_ref"],"o1"); self.assertEqual(len(violation["opaque_entity_ref"]),64)

@override_settings(DEPLOYMENT_ENV="test",SIMULATED_TRADING_ENABLED=True,REAL_TRADING_ENABLED=False,EXTERNAL_EXECUTION_ENABLED=False,REAL_MONEY_ENABLED=False,SIMULATED_EXECUTION_PRICES={"BTC-USD":"100"})
class ReconciliationPersistenceTests(TestCase):
    def test_valid_database_state_persists_immutable_pass_evidence(self):
        user=User.objects.create_user(email="reconcile@example.invalid",phone_number="+12025550199",password=None)
        body,_=create(user,{"instrument":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"1"},"reconcile-valid")
        process_created_order(body["id"],"IMMEDIATE_FULL_FILL")
        report=run(candidate_sha="test-candidate")
        self.assertEqual(report["status"],"PASS"); self.assertEqual(report["violations"],[])
        record=ReconciliationRun.objects.get(pk=report["run_id"]); self.assertEqual(record.status,"PASS"); self.assertEqual(len(record.summary_hash),64)
        record.scope="orders"
        with self.assertRaisesRegex(ValueError,"IMMUTABLE"): record.save()

    def test_correlation_chain_is_preserved_through_settlement(self):
        user=User.objects.create_user(email="correlation@example.invalid",phone_number="+12025550200",password=None)
        correlation="3f25cc00-0fc9-47b6-aa64-393ea50bb726"
        body,_=create(user,{"instrument":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"1"},"correlation-chain",correlation)
        process_created_order(body["id"],"IMMEDIATE_FULL_FILL")
        self.assertEqual(set(str(x) for x in OutboxEvent.objects.filter(payload__order_id=body["id"]).values_list("correlation_id",flat=True)),{correlation})
        self.assertEqual(set(str(x) for x in ApplicationAuditEvent.objects.filter(context__simulation=True,resource_id__in=[body["id"],f"sim:{body['id']}:full"]).values_list("correlation_id",flat=True)),{correlation})
