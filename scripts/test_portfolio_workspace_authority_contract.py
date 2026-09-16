import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE_INSTRUMENTS_PATH = ROOT / "FX/apps/workspace/instruments.py"
WORKSPACE_API_PATH = ROOT / "FX/apps/workspace/api.py"
PORTFOLIO_API_PATH = ROOT / "FX/apps/valuation/portfolio_api.py"
NO_STORE_PATH = ROOT / "FX/middleware/no_store.py"
ENTERPRISE_DOC_PATH = ROOT / "docs/architecture/BEYVRA_ENTERPRISE_EVOLUTION.md"


class PortfolioWorkspaceAuthorityContractTests(unittest.TestCase):
    def setUp(self):
        self.workspace_instruments = WORKSPACE_INSTRUMENTS_PATH.read_text(encoding="utf-8")
        self.workspace_api = WORKSPACE_API_PATH.read_text(encoding="utf-8")
        self.portfolio_api = PORTFOLIO_API_PATH.read_text(encoding="utf-8")
        self.no_store = NO_STORE_PATH.read_text(encoding="utf-8")
        self.enterprise_doc = ENTERPRISE_DOC_PATH.read_text(encoding="utf-8")

    def test_watchlists_keep_canonical_active_instrument_resolution(self):
        self.assertIn("def resolve_active_instrument", self.workspace_instruments)
        self.assertIn("def normalize_removal_reference", self.workspace_instruments)
        self.assertIn('raise InstrumentResolutionError("INSTRUMENT_AMBIGUOUS")', self.workspace_instruments)
        self.assertIn('"INSTRUMENT_AMBIGUOUS": 409', self.workspace_api)

    def test_portfolio_projection_keeps_authoritative_exposure_math(self):
        self.assertIn("SUM_ABSOLUTE_PRICED_POSITION_MARKET_VALUE", self.portfolio_api)
        self.assertIn("largest_position_ratio", self.portfolio_api)
        self.assertIn("advanced_risk_reason", self.portfolio_api)
        self.assertIn("gross exposure as the sum of absolute priced position values", self.enterprise_doc)

    def test_private_no_store_middleware_stays_fail_closed(self):
        self.assertIn("Preserve explicit no-store policies", self.no_store)
        self.assertIn('"Cache-Control"', self.no_store)
        self.assertIn("patch_cache_control(response, private=True, no_store=True)", self.no_store)


if __name__ == "__main__":
    unittest.main()
