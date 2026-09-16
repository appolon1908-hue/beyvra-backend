import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs/architecture/BEYVRA_CONTROL_PLANE_AND_MARKET_AUTHORITY.md"
CONTROL_PLANE_PATH = ROOT / "FX/integrations/control_plane.py"
PRICING_SERVICES_PATH = ROOT / "FX/pricing_authority/services.py"


class ControlPlaneMarketAuthorityContractTests(unittest.TestCase):
    def setUp(self):
        self.doc = DOC_PATH.read_text(encoding="utf-8")
        self.control_plane = CONTROL_PLANE_PATH.read_text(encoding="utf-8")
        self.pricing = PRICING_SERVICES_PATH.read_text(encoding="utf-8")

    def test_doc_keeps_tenant_and_market_fail_closed_contract(self):
        self.assertIn("TENANT_SELECTION_REQUIRED", self.doc)
        self.assertIn("INSTRUMENT_AMBIGUOUS", self.doc)
        self.assertIn("INSTRUMENT_MAPPING_UNAVAILABLE", self.doc)

    def test_control_plane_module_remains_read_only_composition(self):
        self.assertIn('CONTRACT_VERSION = "2026-08-27.v1"', self.control_plane)
        self.assertIn("def _compliance_context", self.control_plane)
        self.assertIn("def _market_data_context", self.control_plane)
        self.assertIn("def build_control_plane_context", self.control_plane)
        self.assertIn('"freshness_policy": "per-response-fail-closed"', self.control_plane)
        self.assertIn('"composition_only": "integrations.control_plane"', self.control_plane)

    def test_pricing_authority_keeps_global_safety_and_tenant_ambiguity_denials(self):
        self.assertIn('{"REAL_TRADING", "REAL_MONEY", "WITHDRAWALS", "DEPOSITS", "TRANSFERS"}', self.pricing)
        self.assertIn('"global-safety-v1"', self.pricing)
        self.assertIn('"tenant-ambiguous-v1"', self.pricing)
        self.assertIn("def market_data_access", self.pricing)


if __name__ == "__main__":
    unittest.main()
