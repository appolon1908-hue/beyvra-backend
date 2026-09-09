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
    "trade.", "order.", "wallet.", "ledger.", "hold.", "payment.",
    "deposit.", "withdrawal.", "transfer.", "custody.", "chain.",
    "broker.", "provider.",
}
PROHIBITED_TOKENS = {value.rstrip(".") for value in PROHIBITED_PREFIXES}
EXPECTED_OPERATIONS = {
    "onboarding.case.create", "compliance.reminder.request", "support.escalation.create",
    "security.alert.create", "report.request.create", "notification.request",
    "crm.projection.request", "webhook.reconciliation.request", "operation.status.read",
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
EXPECTED_EVENTS = {
    "beyvra.account.onboarding_started", "beyvra.account.onboarding_completed",
    "beyvra.account.status_changed", "beyvra.compliance.review_required",
    "beyvra.compliance.document_missing", "beyvra.compliance.review_completed",
    "beyvra.support.case_created", "beyvra.support.case_escalated",
    "beyvra.notification.delivery_failed", "beyvra.notification.preference_changed",
    "beyvra.webhook.delivery_failed", "beyvra.webhook.dead_lettered",
    "beyvra.report.requested", "beyvra.report.ready", "beyvra.security.alert_created",
    "beyvra.demo.session_milestone",
}
EXPECTED_OPENAPI = {
    "/v1/automation/onboarding-cases": {"post": ("createOnboardingCase", WRITE_SCOPE)},
    "/v1/automation/onboarding-cases/{case_id}": {"get": ("getOnboardingCase", READ_SCOPE)},
    "/v1/automation/compliance-tasks/{task_id}/remind": {"post": ("requestComplianceReminder", WRITE_SCOPE)},
    "/v1/automation/support-escalations": {"post": ("createSupportEscalation", WRITE_SCOPE)},
    "/v1/automation/report-requests": {"post": ("createReportRequest", WRITE_SCOPE)},
    "/v1/automation/report-requests/{request_id}": {"get": ("getReportRequest", READ_SCOPE)},
    "/v1/automation/notifications": {"post": ("requestNotification", WRITE_SCOPE)},
    "/v1/automation/security-alerts": {"post": ("createSecurityAlert", WRITE_SCOPE)},
    "/v1/automation/webhook-reconciliation": {"post": ("reconcileWebhookDelivery", WRITE_SCOPE)},
    "/v1/automation/operations/{operation_id}": {"get": ("getAutomationOperation", READ_SCOPE)},
}
EXPECTED_HEADERS = {
    "IdempotencyKey": {"name": "Idempotency-Key", "in": "header", "required": True,
                       "schema": {"type": "string", "maxLength": 255}},
    "RequestId": {"name": "X-Request-ID", "in": "header", "required": True,
                  "schema": {"type": "string", "maxLength": 128}},
    "CorrelationId": {"name": "X-Correlation-ID", "in": "header", "required": False,
                      "schema": {"type": "string", "maxLength": 128}},
}


def fail(message: str) -> None:
    raise SystemExit(f"BEYVRA_INTEGRATION_FABRIC_V2=FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {path}: {exc}")
    require(isinstance(value, dict), f"{path} must contain an object")
    return value


def exact_strings(value: Any, expected: set[str], label: str) -> None:
    require(isinstance(value, list) and all(isinstance(item, str) for item in value),
            f"{label} must be a list of strings")
    require(set(value) == expected and len(value) == len(expected),
            f"{label} must match the reviewed exact allowlist")


def validate_capabilities(name: str, capabilities: Any) -> None:
    require(isinstance(capabilities, dict) and bool(capabilities),
            f"{name} capabilities must be a non-empty object")
    enabled = sorted(key for key, value in capabilities.items() if value is not False)
    require(not enabled, f"{name} enables capabilities: {', '.join(enabled)}")


def has_prohibited_token(value: str) -> bool:
    normalized = value.lower().replace("_", "-")
    tokens = {token for segment in normalized.split(".") for token in segment.split("-") if token}
    return bool(tokens & PROHIBITED_TOKENS)


def _prohibited_prefixes(value, label):
    require(isinstance(value, list) and all(isinstance(item, str) for item in value),
            f"{label} prohibited prefixes must be strings")
    require(PROHIBITED_PREFIXES <= set(value), f"{label} is missing prohibited prefixes")


def validate_fabric() -> dict[str, Any]:
    fabric = load_json(FABRIC_PATH)
    require(fabric.get("schema_version") == "2.0", "unexpected fabric schema version")
    require(fabric.get("source_only") is True, "fabric must remain source-only")
    require(fabric.get("workflow_family") == WORKFLOW_FAMILY, "unexpected workflow family")
    require(fabric.get("machine_client") == MACHINE_CLIENT, "fabric machine client drift")
    require(fabric.get("allowed_command_prefixes") == [ALLOWED_PREFIX], "command prefix is not exact")
    for key in ("direct_n8n_backend_access", "direct_n8n_database_access", "direct_browser_n8n_access"):
        require(fabric.get(key) is False, f"{key} must remain false")
    _prohibited_prefixes(fabric.get("prohibited_command_prefixes"), "fabric")
    validate_capabilities("fabric", fabric.get("capabilities"))
    operations = fabric.get("allowed_operations")
    exact_strings(operations, EXPECTED_OPERATIONS, "allowed_operations")
    for operation in operations:
        require(not has_prohibited_token(operation), f"prohibited operation: {operation}")
    return fabric


def validate_n8n_manifest(fabric: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(N8N_MANIFEST_PATH)
    require(manifest.get("schema_version") == "2.0", "unexpected n8n manifest schema version")
    require(manifest.get("status") == "SOURCE_ONLY", "n8n manifest must remain SOURCE_ONLY")
    require(manifest.get("workflow_family") == WORKFLOW_FAMILY, "n8n workflow family drift")
    require(manifest.get("machine_client") == MACHINE_CLIENT, "n8n manifest machine client drift")
    require(manifest.get("machine_client") == fabric.get("machine_client"), "machine clients disagree")
    require(manifest.get("command_prefixes") == [ALLOWED_PREFIX], "n8n command prefix drift")
    _prohibited_prefixes(manifest.get("prohibited_command_prefixes"), "n8n manifest")
    validate_capabilities("n8n manifest", manifest.get("capabilities"))
    exact_strings(manifest.get("allowed_events"), EXPECTED_EVENTS, "allowed_events")
    commands = manifest.get("allowed_commands")
    exact_strings(commands, EXPECTED_COMMANDS, "allowed_commands")
    for command in commands:
        require(command.startswith(ALLOWED_PREFIX), f"command escapes allowed prefix: {command}")
        require(not has_prohibited_token(command.removeprefix(ALLOWED_PREFIX)),
                f"command disguises a prohibited financial/provider operation: {command}")
    invariants = manifest.get("invariants")
    require(isinstance(invariants, dict), "invariants must be an object")
    for key in (
        "direct_n8n_backend_access", "direct_n8n_database_access", "direct_n8n_broker_access",
        "direct_n8n_payment_access", "financial_effects_allowed", "demo_order_effects_allowed",
        "caller_tenant_authoritative", "workflow_activation_enables_capability", "live_apply_authorized",
    ):
        require(invariants.get(key) is False, f"invariant {key} must remain false")
    for key in ("unknown_outcome_reconciled_before_retry", "exact_replay_returns_original_result",
                "conflicting_replay_rejected"):
        require(invariants.get(key) is True, f"invariant {key} must remain true")
    try:
        readme = N8N_README_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {N8N_README_PATH}: {exc}")
    require(f"machine_client  = {MACHINE_CLIENT}" in readme, "README machine client drift")
    return manifest


def security_scope(operation: dict[str, Any]) -> list[dict[str, list[str]]]:
    value = operation.get("security")
    require(isinstance(value, list), "operation security must be a list")
    return value


def validate_header_components(contract):
    components = contract.get("components")
    require(isinstance(components, dict), "OpenAPI components missing")
    parameters = components.get("parameters")
    require(isinstance(parameters, dict), "command header components missing")
    for key, definition in EXPECTED_HEADERS.items():
        # No unresolved aliases or schema/required/location overrides. A change
        # to these reviewed command identities requires updating this contract.
        require(parameters.get(key) == definition, f"command header definition drift: {key}")
    return parameters


def parameter_refs(operation: dict[str, Any], components=None) -> set[str]:
    parameters = operation.get("parameters", [])
    require(isinstance(parameters, list), "operation parameters must be a list")
    refs, identities = set(), set()
    header_names = {item["name"].casefold() for item in EXPECTED_HEADERS.values()}
    for item in parameters:
        require(isinstance(item, dict), "parameter must be an object")
        if "$ref" in item:
            ref = item["$ref"]
            require(isinstance(ref, str) and ref.startswith("#/components/parameters/"),
                    "unsupported parameter reference")
            key = ref.removeprefix("#/components/parameters/")
            require(components is not None and key in EXPECTED_HEADERS and key in components,
                    f"unresolved command header reference: {ref}")
            require(set(item) == {"$ref"}, "parameter reference must not override header semantics")
            resolved = components[key]
            refs.add(ref)
        else:
            resolved = item
            require(not (item.get("in") == "header" and
                         str(item.get("name", "")).casefold() in header_names),
                    "inline command header override is forbidden")
        name, location = resolved.get("name"), resolved.get("in")
        require(isinstance(name, str) and bool(name) and location in {"path", "query", "header", "cookie"},
                "parameter identity missing")
        identity = (location, name.casefold() if location == "header" else name)
        require(identity not in identities, "duplicate parameter identity")
        identities.add(identity)
    return refs


def validate_openapi() -> None:
    # This .yaml file intentionally contains JSON, valid YAML 1.2.
    contract = load_json(OPENAPI_PATH)
    require(contract.get("openapi") == "3.1.0", "OpenAPI version drift")
    require(contract.get("servers") == [{"url": PRIVATE_SERVER}], "OpenAPI private server drift")
    require("security" not in contract, "OpenAPI must declare least-privilege security per operation")
    paths = contract.get("paths")
    require(isinstance(paths, dict), "OpenAPI paths must be an object")
    require(set(paths) == set(EXPECTED_OPENAPI), "OpenAPI paths must match the reviewed exact allowlist")
    header_components = validate_header_components(contract)
    required_refs = {f"#/components/parameters/{key}" for key in EXPECTED_HEADERS}
    seen_operation_ids = set()
    for path, expected_methods in EXPECTED_OPENAPI.items():
        require(not has_prohibited_token(path), f"prohibited financial/provider token in path: {path}")
        path_item = paths[path]
        require(isinstance(path_item, dict), f"path item must be an object: {path}")
        require(set(path_item) == set(expected_methods), f"unexpected HTTP methods or path overrides: {path}")
        for method, (expected_operation_id, expected_scope) in expected_methods.items():
            operation = path_item[method]
            require(isinstance(operation, dict), f"operation must be an object: {method} {path}")
            require("servers" not in operation, f"operation-level server override: {method} {path}")
            require("callbacks" not in operation, f"unreviewed callback routes: {method} {path}")
            operation_id = operation.get("operationId")
            require(operation_id == expected_operation_id, f"operationId drift: {method} {path}")
            require(operation_id not in seen_operation_ids, f"duplicate operationId: {operation_id}")
            seen_operation_ids.add(operation_id)
            require(not has_prohibited_token(operation_id), f"prohibited operationId: {operation_id}")
            require(security_scope(operation) == [{"oauth2": [expected_scope]}],
                    f"least-privilege scope drift: {method} {path}")
            refs = parameter_refs(operation, header_components)
            if method == "post":
                require(required_refs <= refs, f"command identity headers missing for POST {path}")
    schemes = contract["components"].get("securitySchemes")
    require(isinstance(schemes, dict), "OAuth security schemes missing")
    oauth = schemes.get("oauth2")
    require(isinstance(oauth, dict) and oauth.get("type") == "oauth2", "OAuth scheme type drift")
    flows = oauth.get("flows")
    require(isinstance(flows, dict), "OAuth flows missing")
    credentials = flows.get("clientCredentials")
    require(isinstance(credentials, dict), "OAuth client-credentials flow missing")
    scopes = credentials.get("scopes")
    require(isinstance(scopes, dict) and {READ_SCOPE, WRITE_SCOPE} <= set(scopes),
            "read/write OAuth scopes are incomplete")


def main() -> None:
    fabric = validate_fabric()
    validate_n8n_manifest(fabric)
    validate_openapi()
    print("BEYVRA_INTEGRATION_FABRIC_V2=PASS")


if __name__ == "__main__":
    main()
