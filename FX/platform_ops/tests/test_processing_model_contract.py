from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class ProcessingModelContractTests(SimpleTestCase):
    def test_synchronous_domains_are_explicit_and_not_described_as_workers(self):
        model = (ROOT / "docs/architecture/PROCESSING-AND-WORKER-DEPLOYMENT-MODEL.md").read_text()
        for domain in ("POST_TRADE", "VALUATION", "TREASURY", "REGULATORY_RECORDS"):
            self.assertIn(f"## {domain}", model)
        self.assertEqual(model.count("STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO"), 5)

    def test_chaos_matrix_targets_deployed_boundaries(self):
        matrix = (ROOT / "docs/architecture/CHAOS-AND-RECOVERY-MATRIX.md").read_text()
        for gate in (
            "POST_TRADE_FAILURE_RECOVERY",
            "VALUATION_FAILURE_RECOVERY",
            "TREASURY_FAILURE_RECOVERY",
            "REGULATORY_FAILURE_RECOVERY",
        ):
            self.assertIn(gate, matrix)
        self.assertIn("CHAOS_MATRIX_MATCHES_REAL_ARCHITECTURE=YES", matrix)
        self.assertNotIn("POST_TRADE_WORKER_RECOVERY=PASS", matrix)
        self.assertNotIn("VALUATION_WORKER_RECOVERY=PASS", matrix)
        self.assertNotIn("TREASURY_WORKER_RECOVERY=PASS", matrix)
        self.assertNotIn("REGULATORY_WORKER_RECOVERY=PASS", matrix)

    def test_future_extraction_requires_a_new_certification_cycle(self):
        criteria = (ROOT / "docs/architecture/FUTURE-WORKER-EXTRACTION-CRITERIA.md").read_text()
        self.assertIn("new", criteria.lower())
        for requirement in ("transactional outbox/inbox", "idempotency", "reconciliation", "rollback"):
            self.assertIn(requirement, criteria)
