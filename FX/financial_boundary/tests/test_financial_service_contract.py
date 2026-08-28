import json
from pathlib import Path
import subprocess
import sys
import uuid

from django.test import SimpleTestCase
import yaml

from financial_boundary.contracts import WalletSnapshot


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = ROOT / "contracts" / "financial-service" / "v1"
VALIDATOR = ROOT / "scripts" / "validate_financial_service_contract.py"
SCRATCH_ROOT = ROOT / ".tmp"


def write_scratch_contract(contract: dict) -> Path:
    SCRATCH_ROOT.mkdir(exist_ok=True)
    changed = SCRATCH_ROOT / f"financial-service-contract-{uuid.uuid4()}.yaml"
    changed.write_text(yaml.safe_dump(contract), encoding="utf-8")
    return changed


class FinancialServiceConsumerContractTests(SimpleTestCase):
    def test_pinned_authoritative_snapshot_matches_consumer_expectations(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--require-pinned"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_breaking_scope_change_fails_validation(self):
        contract = yaml.safe_load((CONTRACT_ROOT / "openapi.yaml").read_text(encoding="utf-8"))
        contract["paths"]["/wallets"]["get"]["x-required-scope"] = "financial.owner"
        changed = write_scratch_contract(contract)
        try:
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), "--contract", str(changed)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            changed.unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scope changed for GET /wallets", result.stderr)

    def test_new_owner_operation_requires_explicit_client_review(self):
        contract = yaml.safe_load((CONTRACT_ROOT / "openapi.yaml").read_text(encoding="utf-8"))
        contract["paths"]["/settlements"] = {"post": {"responses": {"503": {"description": "disabled"}}}}
        changed = write_scratch_contract(contract)
        try:
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), "--contract", str(changed)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            changed.unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owner contract appeared for POST /settlements", result.stderr)

    def test_wallet_fixture_satisfies_application_money_contract(self):
        fixture = json.loads((CONTRACT_ROOT / "fixtures" / "wallet-snapshot.json").read_text(encoding="utf-8"))
        snapshot = WalletSnapshot(**fixture)
        self.assertEqual(snapshot.available, "100.43000000")

    def test_feature_disabled_fixture_has_stable_safe_shape(self):
        fixture = json.loads((CONTRACT_ROOT / "fixtures" / "feature-disabled.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["status"], 503)
        self.assertEqual(fixture["code"], "FEATURE_DISABLED")
        self.assertEqual(fixture["errors"], [])
