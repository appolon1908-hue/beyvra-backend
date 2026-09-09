#!/usr/bin/env python3
"""Fail-closed validation for the source-only Beyvra automation contract."""

from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FABRIC_PATH = ROOT / "contracts/automation/beyvra-fabric.v2.json"
N8N_MANIFEST_PATH = ROOT / "docs/integrations/n8n/manifest.v2.json"
OPENAPI_PATH = ROOT / "contracts/automation/beyvra-operations-api.v1.yaml"

ALLOWED_PREFIX = "beyvra.operations."
WORKFLOW_FAMILY = "product.beyvra-nonfinancial"
PROHIBITED_PREFIXES = {
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
PROHIBITED_PATH_TERMS = {
    "trade",
    "order",
    "wallet",
    "ledger",
    "payment",
    "deposit",
    "withdrawal",
    "transfer",
    "custody",
    "chain",
    "broker",
    "provider",
}


def fail(message: str) -> None:
    raise SystemExit(f"BEYVRA_INTEGRATION_FABRIC_V2=FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {path.relative_to(ROOT)}: {exc}")
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_capabilities(name: str, capabilities: Any) -> None:
    require(isinstance(capabilities, dict) and capabilities, f"{name} capabilities must be a non-empty object")
    enabled = sorted(key for key, value in capabilities.items() if value is not False)
    require(not enabled, f"{name} enables capabilities: {', '.join(enabled)}")


def validate_fabric() -> None:
    fabric = load_json(FABRIC_PATH)
    require(fabric.get("schema_version") == "2.0", "unexpected fabric schema version")
    require(fabric.get("source_only") is True, "fabric must remain source-only")
    require(fabric.get("workflow_family") == WORKFLOW_FAMILY, "unexpected workflow family")
    require(fabric.get("allowed_command_prefixes") == [ALLOWED_PREFIX], "command prefix is not exact")

    for key in (
        "direct_n8n_backend_access",
        "direct_n8n_database_access",
        "direct_browser_n8n_access",
    ):
        require(fabric.get(key) is False, f"{key} must remain false")

    prohibited = set(fabric.get("prohibited_command_prefixes", []))
    require(PROHIBITED_PREFIXES <= prohibited, "fabric is missing prohibited command prefixes")
    validate_capabilities("fabric", fabric.get("capabilities"))

    operations = fabric.get("allowed_operations")
    require(isinstance(operations, list) and operations, "allowed_operations must be non-empty")
    for operation in operations:
        require(isinstance(operation, str) and operation.strip(), "allowed operation must be a string")
        require(
            not any(operation.startswith(prefix) for prefix in prohibited),
            f"allowed operation uses prohibited prefix: {operation}",
        )


def validate_n8n_manifest() -> None:
    manifest = load_json(N8N_MANIFEST_PATH)
    fabric = load_json(FABRIC_PATH)
    require(manifest.get("machine_client") == fabric.get("machine_client") == "n8n-product-automation", "machine-client identity drift")
    require(manifest.get("schema_version") == "2.0", "unexpected n8n manifest schema version")
    require(manifest.get("status") == "SOURCE_ONLY", "n8n manifest must remain SOURCE_ONLY")
    require(manifest.get("workflow_family") == WORKFLOW_FAMILY, "n8n workflow family drift")
    require(manifest.get("command_prefixes") == [ALLOWED_PREFIX], "n8n command prefix drift")

    prohibited = set(manifest.get("prohibited_command_prefixes", []))
    require(PROHIBITED_PREFIXES <= prohibited, "n8n manifest is missing prohibited prefixes")
    validate_capabilities("n8n manifest", manifest.get("capabilities"))

    commands = manifest.get("allowed_commands")
    require(isinstance(commands, list) and commands, "allowed_commands must be non-empty")
    for command in commands:
        require(isinstance(command, str), "allowed command must be a string")
        require(command.startswith(ALLOWED_PREFIX), f"command escapes allowed prefix: {command}")
        require(
            not any(command.startswith(prefix) for prefix in prohibited),
            f"command uses prohibited prefix: {command}",
        )

    invariants = manifest.get("invariants")
    require(isinstance(invariants, dict), "invariants must be an object")
    for key in (
        "direct_n8n_backend_access",
        "direct_n8n_database_access",
        "direct_n8n_broker_access",
        "direct_n8n_payment_access",
        "financial_effects_allowed",
        "demo_order_effects_allowed",
        "workflow_activation_enables_capability",
        "live_apply_authorized",
    ):
        require(invariants.get(key) is False, f"invariant {key} must remain false")
    for key in (
        "unknown_outcome_reconciled_before_retry",
        "exact_replay_returns_original_result",
        "conflicting_replay_rejected",
    ):
        require(invariants.get(key) is True, f"invariant {key} must remain true")


def validate_openapi() -> None:
    try:
        document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"cannot parse OpenAPI: {exc}")
    require(isinstance(document, dict), "OpenAPI must be an object")
    require(document.get("openapi") == "3.1.0", "OpenAPI version drift")
    require(document.get("servers") == [{"url": "https://beyvra.internal.invalid"}], "OpenAPI server must remain private/non-routable")
    paths = document.get("paths")
    require(isinstance(paths, dict) and paths, "OpenAPI contains no paths")
    operation_ids = set()
    for path, item in paths.items():
        require(isinstance(path, str) and path.startswith("/v1/automation/"), f"path escapes automation namespace: {path}")
        require(not any(term in path.lower() for term in PROHIBITED_PATH_TERMS), f"prohibited financial/provider term in path: {path}")
        require(isinstance(item, dict) and item, "path item must be an object")
        for method, operation in item.items():
            require(method in {"get", "post"}, f"unsupported path operation: {method}")
            require(isinstance(operation, dict), "operation must be an object")
            operation_id = operation.get("operationId")
            require(isinstance(operation_id, str) and operation_id, "operationId is required")
            require(operation_id not in operation_ids, "OpenAPI operationId values must be unique")
            operation_ids.add(operation_id)
            require(not any(term in operation_id.lower() for term in PROHIBITED_PATH_TERMS), f"prohibited financial/provider term in operationId: {operation_id}")
            scope = "read" if method == "get" else "write"
            require(operation.get("security", document.get("security")) == [{"oauth2": [f"beyvra.operations.{scope}"]}], f"incorrect {method} scope")
            if method == "post":
                body = operation.get("requestBody", {})
                require(body.get("required") is True, "mutation body must be required")
                schema = body.get("content", {}).get("application/json", {}).get("schema", {})
                require(schema.get("type") == "object" and schema.get("required"), "mutation input schema must require fields")
                require(all(name in schema.get("properties", {}) for name in schema["required"]), "required input property is undefined")
                parameters = []
                for parameter in operation.get("parameters", []):
                    if "$ref" in parameter:
                        prefix = "#/components/parameters/"
                        require(parameter["$ref"].startswith(prefix), "unsupported parameter reference")
                        parameter = document.get("components", {}).get("parameters", {}).get(parameter["$ref"][len(prefix):], {})
                    parameters.append(parameter)
                required_headers = {"Idempotency-Key", "X-Request-ID"}
                if operation_id in {"requestComplianceReminder", "createSupportEscalation", "reconcileWebhookDelivery"}:
                    required_headers.add("If-Match")
                headers = {p.get("name") for p in parameters if p.get("in") == "header" and p.get("required") is True}
                require(required_headers <= headers, "mutation safety headers are missing")


def main() -> None:
    validate_fabric()
    validate_n8n_manifest()
    validate_openapi()
    print("BEYVRA_INTEGRATION_FABRIC_V2=PASS")


if __name__ == "__main__":
    main()
