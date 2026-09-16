import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts/openapi/beyvra-enterprise-experience-v1.yaml"
ARCH_PATH = ROOT / "docs/architecture/BEYVRA_ENTERPRISE_EVOLUTION.md"


class EnterpriseExperienceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
        self.architecture = ARCH_PATH.read_text(encoding="utf-8")

    def test_contract_keeps_enterprise_workspace_and_operator_paths(self):
        expected_paths = {
            "/watchlists",
            "/watchlists/{watchlist_id}",
            "/watchlists/{watchlist_id}/items",
            "/alerts",
            "/alerts/{alert_id}",
            "/portfolio/summary",
            "/portfolio/positions",
            "/portfolio/performance",
            "/portfolio/allocations",
            "/portfolio/risk",
            "/portfolio/evidence-quality",
            "/operator/orders",
            "/operator/providers/health",
            "/operator/reconciliation/breaks",
            "/operator/halts",
            "/operator/limits/proposals",
        }
        self.assertEqual(self.contract["servers"], [{"url": "/api/v1"}])
        self.assertEqual(self.contract["security"], [{"cookieSession": []}])
        self.assertTrue(expected_paths.issubset(self.contract["paths"]))

    def test_portfolio_contract_remains_fail_closed_on_missing_evidence(self):
        summary = self.contract["paths"]["/portfolio/summary"]["get"]["responses"]["200"]["description"]
        evidence = self.contract["paths"]["/portfolio/evidence-quality"]["get"]["responses"]["200"]["description"]
        self.assertIn("missing evidence is unpriced", summary.lower())
        self.assertIn("without estimated values", evidence.lower())

    def test_architecture_doc_keeps_simulation_only_and_fail_closed_guards(self):
        self.assertIn("Status: implementation baseline, simulation-only.", self.architecture)
        self.assertIn("Every real-value and external-execution capability is fail-closed.", self.architecture)
        self.assertIn("The first enterprise API baseline adds tenant-scoped watchlists", self.architecture)


if __name__ == "__main__":
    unittest.main()
