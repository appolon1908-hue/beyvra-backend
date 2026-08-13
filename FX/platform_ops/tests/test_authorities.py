from decimal import Decimal
from unittest.mock import Mock
from django.test import SimpleTestCase,TestCase
from platform_ops.backpressure.controllers import BackpressureController
from platform_ops.capacity.services import CapacityAuthority
from platform_ops.capacity.profiles import may_advance
from platform_ops.capacity.runners import run_fixture
from platform_ops.degraded_mode.resolver import OperationalModeResolver
from platform_ops.dependency_failure.evaluators import DependencyFailureEvaluator
from platform_ops.evidence.hashes import root_hash
from platform_ops.evidence.models import OperationalEvidenceManifest
from platform_ops.feature_flags.evaluator import HIGH_RISK,evaluate,inspect
from platform_ops.kill_switch.hierarchy import effective_active
from platform_ops.observability.logging import redact
from platform_ops.reconciliation.invariants import CHECKS,summarize
from platform_ops.release.validators import validate_manifest

class FailClosedAuthorityTests(SimpleTestCase):
    def test_all_high_risk_flags_fail_closed_for_missing_malformed_and_true(self):
        for code in HIGH_RISK:
            self.assertFalse(evaluate(code,None));self.assertFalse(evaluate(code,"true"));self.assertFalse(evaluate(code,True))
    def test_unknown_high_risk_kill_switch_is_active(self):self.assertTrue(effective_active({"GLOBAL_PLATFORM_HALT":"INACTIVE"},"TRADING_HALT"))
    def test_unknown_global_halt_is_active(self):self.assertTrue(effective_active({},"TRADING_HALT"))
    def test_operational_mode_unknown_halt_is_halted(self):self.assertEqual(OperationalModeResolver.resolve({}),"HALTED")
    def test_halted_disallows_simulation(self):self.assertFalse(OperationalModeResolver.allows("HALTED","simulate"))
    def test_dependency_failure_policy_fails_closed(self):
        p=Mock(allowed_mode="READ_ONLY",fail_closed=True,fallback="OUTBOX");self.assertFalse(DependencyFailureEvaluator.evaluate(p,False)["allowed"])
    def test_committed_events_cannot_be_dropped(self):self.assertFalse(BackpressureController.may_drop("COMMITTED_STATE"))
    def test_only_noncritical_telemetry_can_drop(self):self.assertTrue(BackpressureController.may_drop("NONCRITICAL_TELEMETRY"))
    def test_reconciliation_requires_complete_evidence(self):self.assertEqual(summarize({})["state"],"INCOMPLETE")
    def test_reconciliation_zero_tolerance(self):self.assertEqual(summarize({key:0 for key in CHECKS})["state"],"PASS")
    def test_every_reconciliation_mismatch_fails(self):
        for check in CHECKS:
            results={key:0 for key in CHECKS};results[check]=1
            self.assertEqual(summarize(results)["state"],"FAIL")
    def test_log_redaction_is_recursive(self):self.assertEqual(redact({"api_token":"x","nested":{"password":"y"}}),{"api_token":"[REDACTED]","nested":{"password":"[REDACTED]"}})
    def test_release_rejects_missing_hashes(self):
        with self.assertRaises(ValueError):validate_manifest({})
    def test_release_rejects_mutable_image(self):
        h="a"*64;v={k:h for k in ("backend_sha","migration_hash","openapi_hash","sbom_hash","configuration_hash","feature_flag_policy_hash","test_evidence_hash","security_evidence_hash")};v["image_digests"]={"backend":"latest"}
        with self.assertRaises(ValueError):validate_manifest(v)
    def test_evidence_root_is_order_stable(self):self.assertEqual(root_hash({"a":1,"b":2}),root_hash({"b":2,"a":1}))
    def test_unsafe_high_risk_configuration_is_visible(self):self.assertTrue(inspect("REAL_MONEY_ENABLED",True)["unsafe_configuration"])
    def test_load_profiles_cannot_skip_levels(self):self.assertFalse(may_advance("BASELINE","5X",True))
    def test_load_profile_stops_when_unhealthy(self):self.assertFalse(may_advance("BASELINE","1X",False))
    def test_fixture_runner_reports_all_operations(self):self.assertEqual(run_fixture(lambda:None,100)["count"],100)

class CapacityTests(TestCase):
    def test_evidence_required(self):
        with self.assertRaises(ValueError):CapacityAuthority.certify(tested_limit=100,service_code="api",resource_type="API_RPS",environment="TEST",unit="rps",test_sha="",evidence_ref="",tested_at="2026-08-11T00:00:00Z")
    def test_safety_margin_below_tested_limit(self):
        x=CapacityAuthority.certify(tested_limit=100,service_code="api",resource_type="API_RPS",environment="TEST",unit="rps",test_sha="a"*40,evidence_ref="evidence/test.json",tested_at="2026-08-11T00:00:00Z")
        self.assertEqual(x.safe_operating_limit,Decimal("70.00"))

class EvidenceIntegrityTests(TestCase):
    def test_manifest_root_is_calculated_and_manifest_is_immutable(self):
        values={field:"a"*64 for field in ("candidate_hash","service_inventory_hash","config_hash","migration_hash","openapi_hash","sbom_hash","test_hash","chaos_hash","restore_hash","reconciliation_hash")}
        manifest=OperationalEvidenceManifest.objects.create(release_id="00000000-0000-0000-0000-000000000001",manifest_version="v1",**values)
        self.assertEqual(len(manifest.root_hash),64)
        manifest.test_hash="b"*64
        with self.assertRaises(ValueError):manifest.save()
