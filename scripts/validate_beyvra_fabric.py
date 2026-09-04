#!/usr/bin/env python3
"""Fail-closed validation for the source-only Beyvra automation contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FABRIC_PATH = ROOT / "contracts/automation/beyvra-fabric.v2.json"
N8N_MANIFEST_PATH = ROOT / "docs/integrations/n8n/manifest.v2.json"
N8N_README_PATH = ROOT / "docs/integrations/n8n/README.md"
OPENAPI_PATH = ROOT / "contracts/automation/beyvra-operations-api.v1.yaml"

ALLOWED_PREFIX = "beyvra.operations."
WORKFLOW_FAMILY = "product.beyvra-nonfinancial"
MACHINE_CLIENT = "n8n-product-automation"
PRIVATE_SERVER = "https://beyvra.internal.invalid"
WRITE_SCOPE = "beyvra.operations.write"
READ_SCOPE = "beyvra.operations.read"

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
PROHIBITED_TOKENS = {
    value.rstrip(".") for value in PROHIBITED_PREFIXES
}

EXPECTED_OPERATIONS = {
    "onboarding.case.create",
    "compliance.reminder.request",
    "support.escalation.create",
    "security.alert.create",
    "report.request.create",
    "notification.request",
    "crm.projection.request",
    "webhook.reconciliation.request",
    "operation.status.read",
}
EXPECTED_COMMANDS = {
    "beyvra.operations.onboarding-task.create.v1",
    "beyvra.operations.compliance-reminder.request.v1",
    "beyvra.operations.support-escalation.create.v1",
    "beyvra.operations.internal-alert.request.v1",
    "beyvra.operations.notification.request.v1",
    "beyvra.operations.report-generation.request.v1",
    "beyvra.operations.report-status.read.v1",
    "beyvra.operations.webhook-delivery.read.v1",
    "beyvra.operations.webhook-retry.request.v1",
    "beyvra.operations.crm-projection.request.v1",
}
EXPECTED_OPENAPI = {
    "/v1/automation/onboarding-cases": {
        "post": ("createOnboardingCase", WRITE_SCOPE),
    },
    "/v1/automation/onboarding-cases/{case_id}": {
        "get": ("getOnboardingCase", READ_SCOPE),
    },
    "/v1/automation/compliance-tasks/{task_id}/remind": {
        "post": ("requestComplianceReminder", WRITE_SCOPE),
    },
    "/v1/automation/support-escalations": {
        "post": ("createSupportEscalation", WRITE_SCOPE),
    },
    "/v1/automation/report-requests": {
        "post": ("createReportRequest", WRITE_SCOPE),
    },
    "/v1/automation/report-requests/{request_id}": {
        "get": ("getReportRequest", READ_SCOPE),
    },
    "/v1/automation/notifications": {
        "post": ("requestNotification", WRITE_SCOPE),
    },
    "/v1/automation/security-alerts": {
        "post": ("createSecurityAlert", WRITE_SCOPE),
    },
    "/v1/automation/webhook-reconciliation": {
        "post": ("reconcileWebhookDelivery", WRITE_SCOPE),
    },
    "/v1/automation/operations/{operation_id}": {
        "get": ("getAutomationOperation", READ_SCOPE),
    },
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
    require(
        isinstance(value, dict),
        f"{path.relative_to(ROOT)} must contain an object",
    )
    return value


def validate_capabilities(name: str, capabilities: Any) -> None:
    require(
        isinstance(capabilities, dict) and capabilities,
        f"{name} capabilities must be a non-empty object",
    )
    enabled = sorted(
        key for key, value in capabilities.items() if value is not False
    )
    require(not enabled, f"{name} enables capabilities: {', '.join(enabled)}")


def has_prohibited_token(value: str) -> bool:
    normalized = value.lower().replace("_", "-")
    tokens = {
        token
        for segment in normalized.split(".")
        for token in segment.split("-")
        if token
    }
    return bool(tokens & PROHIBITED_TOKENS)


def validate_fabric() -> dict[str, Any]:
    fabric = load_json(FABRIC_PATH)
    require(
        fabric.get("schema_version") == "2.0",
        "unexpected fabric schema version",
    )
    require(fabric.get("source_only") is True, "fabric must remain source-only")
    require(
        fabric.get("workflow_family") == WORKFLOW_FAMILY,
        "unexpected workflow family",
    )
    require(
        fabric.get("machine_client") == MACHINE_CLIENT,
        "fabric machine client drift",
    )
    require(
        fabric.get("allowed_command_prefixes") == [ALLOWED_PREFIX],
        "command prefix is not exact",
    )

    for key in (
        "direct_n8n_backend_access",
        "direct_n8n_database_access",
        "direct_browser_n8n_access",
    ):
        require(fabric.get(key) is False, f"{key} must remain false")

    prohibited = set(fabric.get("prohibited_command_prefixes", []))
    require(
        PROHIBITED_PREFIXES <= prohibited,
        "fabric is missing prohibited command prefixes",
    )
    validate_capabilities("fabric", fabric.get("capabilities"))

    operations = fabric.get("allowed_operations")
    require(
        isinstance(operations, list),
        "allowed_operations must be a list",
    )
    require(
        set(operations) == EXPECTED_OPERATIONS
        and len(operations) == len(EXPECTED_OPERATIONS),
        "allowed_operations must match the reviewed exact allowlist",
    )
    for operation in operations:
        require(
            isinstance(operation, str) and operation.strip(),
            "allowed operation must be a non-empty string",
        )
        require(
            not has_prohibited_token(operation),
            f"allowed operation contains a prohibited financial/provider token: {operation}",
        )
    return fabric


def validate_n8n_manifest(fabric: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(N8N_MANIFEST_PATH)
    require(
        manifest.get("schema_version") == "2.0",
        "unexpected n8n manifest schema version",
    )
    require(
        manifest.get("status") == "SOURCE_ONLY",
        "n8n manifest must remain SOURCE_ONLY",
    )
    require(
        manifest.get("workflow_family") == WORKFLOW_FAMILY,
        "n8n workflow family drift",
    )
    require(
        manifest.get("machine_client") == MACHINE_CLIENT,
        "n8n manifest machine client drift",
    )
    require(
        manifest.get("machine_client") == fabric.get("machine_client"),
        "fabric and n8n manifest machine clients disagree",
    )
    require(
        manifest.get("command_prefixes") == [ALLOWED_PREFIX],
        "n8n command prefix drift",
    )

    prohibited = set(manifest.get("prohibited_command_prefixes", []))
    require(
        PROHIBITED_PREFIXES <= prohibited,
        "n8n manifest is missing prohibited prefixes",
    )
    validate_capabilities("n8n manifest", manifest.get("capabilities"))

    commands = manifest.get("allowed_commands")
    require(isinstance(commands, list), "allowed_commands must be a list")
    require(
        set(commands) == EXPECTED_COMMANDS
        and len(commands) == len(EXPECTED_COMMANDS),
        "allowed_commands must match the reviewed exact allowlist",
    )
    for command in commands:
        require(
            isinstance(command, str) and command.startswith(ALLOWED_PREFIX),
            f"command escapes allowed prefix: {command}",
        )
        suffix = command.removeprefix(ALLOWED_PREFIX)
        require(
            not has_prohibited_token(suffix),
            f"command disguises a prohibited financial/provider operation: {command}",
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

    try:
        readme = N8N_README_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read {N8N_README_PATH.relative_to(ROOT)}: {exc}")
    require(
        f"machine_client  = {MACHINE_CLIENT}" in readme,
        "README machine client drift",
    )
    return manifest


def security_scope(operation: dict[str, Any]) -> list[dict[str, list[str]]]:
    value = operation.get("security")
    require(isinstance(value, list), "operation security must be a list")
    return value


def parameter_refs(operation: dict[str, Any]) -> set[str]:
    parameters = operation.get("parameters", [])
    require(isinstance(parameters, list), "operation parameters must be a list")
    return {
        item.get("$ref")
        for item in parameters
        if isinstance(item, dict) and isinstance(item.get("$ref"), str)
    }


def validate_openapi() -> None:
    # The .yaml extension is kept for OpenAPI tooling, but the document is
    # intentionally JSON (valid YAML 1.2). Parsing it structurally with the
    # standard library prevents quoted-path or indentation bypasses.
    contract = load_json(OPENAPI_PATH)
    require(contract.get("openapi") == "3.1.0", "OpenAPI version drift")
    require(
        contract.get("servers") == [{"url": PRIVATE_SERVER}],
        "OpenAPI server must remain the exact private/non-routable endpoint",
    )
    require(
        "security" not in contract,
        "OpenAPI must declare least-privilege security per operation",
    )

    paths = contract.get("paths")
    require(isinstance(paths, dict), "OpenAPI paths must be an object")
    require(
        set(paths) == set(EXPECTED_OPENAPI),
        "OpenAPI paths must match the reviewed exact allowlist",
    )

    seen_operation_ids: set[str] = set()
    required_command_refs = {
        "#/components/parameters/IdempotencyKey",
        "#/components/parameters/RequestId",
        "#/components/parameters/CorrelationId",
    }

    for path, expected_methods in EXPECTED_OPENAPI.items():
        require(
            not has_prohibited_token(path),
            f"prohibited financial/provider token in path: {path}",
        )
        path_item = paths[path]
        require(isinstance(path_item, dict), f"path item must be an object: {path}")
        require(
            set(path_item) == set(expected_methods),
            f"unexpected HTTP methods for {path}",
        )

        for method, (expected_operation_id, expected_scope) in expected_methods.items():
            operation = path_item[method]
            require(
                isinstance(operation, dict),
                f"{method.upper()} {path} must be an object",
            )
            operation_id = operation.get("operationId")
            require(
                operation_id == expected_operation_id,
                f"operationId drift for {method.upper()} {path}",
            )
            require(
                operation_id not in seen_operation_ids,
                f"duplicate OpenAPI operationId: {operation_id}",
            )
            seen_operation_ids.add(operation_id)
            require(
                not has_prohibited_token(operation_id),
                f"prohibited financial/provider token in operationId: {operation_id}",
            )
            require(
                security_scope(operation) == [{"oauth2": [expected_scope]}],
                f"least-privilege scope drift for {method.upper()} {path}",
            )
            if method == "post":
                require(
                    required_command_refs <= parameter_refs(operation),
                    f"command identity headers missing for POST {path}",
                )

    flows = (
        contract.get("components", {})
        .get("securitySchemes", {})
        .get("oauth2", {})
        .get("flows", {})
        .get("clientCredentials", {})
    )
    scopes = flows.get("scopes") if isinstance(flows, dict) else None
    require(isinstance(scopes, dict), "OAuth client-credentials scopes missing")
    require(
        {READ_SCOPE, WRITE_SCOPE} <= set(scopes),
        "read/write OAuth scopes are incomplete",
    )


def main() -> None:
    fabric = validate_fabric()
    validate_n8n_manifest(fabric)
    validate_openapi()
    print("BEYVRA_INTEGRATION_FABRIC_V2=PASS")


if __name__ == "__main__":
    main()
