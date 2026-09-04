#!/usr/bin/env python3
"""Validate the source-only Beyvra ↔ Middleware ↔ n8n contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FABRIC_PATH = ROOT / "contracts/automation/beyvra-fabric.v2.json"
MANIFEST_PATH = ROOT / "docs/integrations/n8n/manifest.v2.json"
OPENAPI_PATH = ROOT / "contracts/automation/beyvra-operations-api.v1.yaml"

fabric = json.loads(FABRIC_PATH.read_text(encoding="utf-8"))
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
openapi = OPENAPI_PATH.read_text(encoding="utf-8")

assert fabric["schema_version"] == "2.0"
assert manifest["schema_version"] == "2.0"
assert fabric["source_only"] is True
assert manifest["status"] == "SOURCE_ONLY"
assert fabric["workflow_family"] == manifest["workflow_family"] == "product.beyvra-nonfinancial"
assert fabric["machine_client"] == manifest["machine_client"] == "n8n-product-automation"
assert fabric["allowed_command_prefixes"] == manifest["command_prefixes"] == ["beyvra.operations."]

for key in (
    "direct_n8n_backend_access",
    "direct_n8n_database_access",
    "direct_browser_n8n_access",
):
    assert fabric[key] is False

assert manifest["invariants"]["direct_n8n_backend_access"] is False
assert manifest["invariants"]["direct_n8n_database_access"] is False
assert manifest["invariants"]["financial_effects_allowed"] is False
assert manifest["invariants"]["demo_order_effects_allowed"] is False
assert manifest["invariants"]["live_apply_authorized"] is False

required_prohibited = {
    "trade.",
    "order.",
    "wallet.",
    "ledger.",
    "hold.",
    "payment.",
    "deposit.",
    "withdrawal.",
    "transfer.",
    "custody.",
    "chain.",
    "broker.",
    "provider.",
}
assert required_prohibited.issubset(set(fabric["prohibited_command_prefixes"]))
assert required_prohibited.issubset(set(manifest["prohibited_command_prefixes"]))

assert all(value is False for value in fabric["capabilities"].values())
assert all(value is False for value in manifest["capabilities"].values())
assert fabric["capabilities"] == manifest["capabilities"]

for command in manifest["allowed_commands"]:
    assert command.startswith("beyvra.operations.")
    assert not any(command.startswith(prefix) for prefix in required_prohibited)

assert "openapi: 3.1.0" in openapi
assert "https://beyvra.internal.invalid" in openapi
assert "beyvra.operations.write" in openapi
assert "/v1/automation/" in openapi

print("BEYVRA_INTEGRATION_FABRIC_V2=PASS")
