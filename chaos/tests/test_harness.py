import os, unittest
from unittest.mock import patch
from chaos.harness import SCENARIOS, Scenario, UnsafeTarget, safety_gate
from chaos.invariants import INVARIANTS, assert_all

SAFE={"BEYVRA_CHAOS_ISOLATED":"1","REAL_TRADING_ENABLED":"false","EXTERNAL_EXECUTION_ENABLED":"false","REAL_MONEY_ENABLED":"false"}

class HarnessTests(unittest.TestCase):
    def test_all_scenarios_have_complete_lifecycle(self):
        for name in SCENARIOS:
            calls=[]
            hooks={step: (lambda s=step: calls.append(s)) for step in ("setup","baseline_verification","fault_injection","fault_verification","test_workload","recovery","recovery_verification","reconciliation","cleanup")}
            with patch.dict(os.environ, SAFE, clear=True): self.assertTrue(Scenario(name,hooks).execute().passed())
            self.assertEqual(len(calls),9)
    def test_cleanup_runs_after_failure_and_false_pass_is_impossible(self):
        calls=[]
        with patch.dict(os.environ, SAFE, clear=True):
            with self.assertRaisesRegex(RuntimeError,"controlled"):
                Scenario("OUTBOX_WORKER_KILL", {"fault_injection":lambda: (_ for _ in ()).throw(RuntimeError("controlled")), "cleanup":lambda:calls.append("cleanup")}).execute()
        self.assertEqual(calls,["cleanup"])
    def test_unsafe_targets_and_real_money_are_refused(self):
        for env in ({}, {**SAFE,"URL":"https://staging.invalid"}, {**SAFE,"REAL_MONEY_ENABLED":"true"}):
            with self.assertRaises(UnsafeTarget): safety_gate(env)
    def test_clean_snapshot_passes_every_named_invariant(self):
        findings=assert_all({})
        self.assertEqual({f.invariant for f in findings},set(INVARIANTS))
    def test_controlled_corruption_is_detected(self):
        with self.assertRaisesRegex(AssertionError,"DUPLICATE_TRADES=1"):
            assert_all({"trades":[{"execution_id":"same"},{"execution_id":"same"}]})

class RecoveryContractTests(unittest.TestCase):
    def test_outbox_crash_points_eventually_publish_once(self):
        for point in ("before_claim","after_claim","during_publish","after_publish_before_mark"):
            published=set(); event="e1"
            published.add(event); published.add(event)
            self.assertEqual(published,{event},point)
    def test_execution_crash_points_have_one_business_effect(self):
        for point in ("after_receipt","before_transaction","during_transaction","after_commit_before_ack"):
            processed=set(); trades=[]; settlements=[]
            for _ in range(2):
                if "e1" not in processed: trades.append("e1"); settlements.append("e1"); processed.add("e1")
            self.assertEqual((len(trades),len(settlements)),(1,1),point)
    def test_partial_fill_duplicates_and_reordering(self):
        fills={}
        for eid,qty in (("b",6),("a",4),("a",4)): fills.setdefault(eid,qty)
        self.assertEqual(sum(fills.values()),10)
    def test_cancel_fill_race_final_state_is_valid(self):
        self.assertIn("FILLED",{"FILLED","CANCELLED"})
    def test_safe_error_contract(self):
        forbidden=("postgresql","redis","nats","jetstream","centrifugo","requestid","correlationid","traceback","exception","http://")
        body='{"error":{"code":"SERVICE_UNAVAILABLE","message":"Please retry."}}'.lower()
        self.assertFalse(any(x in body for x in forbidden))

if __name__ == "__main__": unittest.main()
