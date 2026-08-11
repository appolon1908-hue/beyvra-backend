#!/usr/bin/env python3
"""Validate Beyvra consumer assumptions against Financial Service OpenAPI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "financial-service" / "v1"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(contract_path: Path, *, require_pinned: bool = False) -> list[str]:
    expectations = _load_json(CONTRACT_ROOT / "consumer-expectations.json")
    source = _load_json(CONTRACT_ROOT / "source.json")
    raw = contract_path.read_bytes()
    contract = yaml.safe_load(raw)
    errors: list[str] = []

    if require_pinned:
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != source["sha256"]:
            errors.append(f"snapshot SHA-256 changed: {actual_hash}")

    if contract.get("openapi") != "3.1.0":
        errors.append("OpenAPI version must remain 3.1.0")
    if contract.get("info", {}).get("version") != expectations["openapi_info_version"]:
        errors.append("Financial Service info.version changed")

    security_schemes = contract.get("components", {}).get("securitySchemes", {})
    scheme = expectations["required_security_scheme"]
    if security_schemes.get(scheme, {}).get("type") != "mutualTLS":
        errors.append("mutualTLS security scheme is missing or changed")

    paths = contract.get("paths", {})
    for expected in expectations["operations"]:
        path, method = expected["path"], expected["method"]
        operation = paths.get(path, {}).get(method)
        label = f"{method.upper()} {path}"
        if operation is None:
            errors.append(f"required operation removed: {label}")
            continue
        if expected.get("scope") != operation.get("x-required-scope"):
            errors.append(f"scope changed for {label}")
        actual_responses = set(operation.get("responses", {}))
        missing_responses = set(expected["responses"]) - actual_responses
        if missing_responses:
            errors.append(f"responses removed from {label}: {sorted(missing_responses)}")
        if expected.get("idempotency_required"):
            parameters = operation.get("parameters", [])
            if not any(parameter.get("$ref", "").endswith("/IdempotencyKey") for parameter in parameters):
                errors.append(f"Idempotency-Key requirement removed from {label}")

    for absent in expectations["required_absent_operations"]:
        if absent["method"] in paths.get(absent["path"], {}):
            errors.append(
                f"owner contract appeared for {absent['method'].upper()} {absent['path']}; "
                "review and replace the local fail-closed stub before accepting the new contract"
            )

    problem = contract.get("components", {}).get("schemas", {}).get("Problem", {})
    required_problem_fields = {"type", "title", "status", "detail", "code", "request_id", "errors"}
    if not required_problem_fields.issubset(problem.get("required", [])):
        errors.append("Problem response required fields changed")
    error_codes = set(problem.get("properties", {}).get("code", {}).get("enum", []))
    missing_codes = set(expectations["required_error_codes"]) - error_codes
    if missing_codes:
        errors.append(f"required error codes removed: {sorted(missing_codes)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=CONTRACT_ROOT / "openapi.yaml",
        help="authoritative or snapshotted Financial Service OpenAPI file",
    )
    parser.add_argument(
        "--require-pinned",
        action="store_true",
        help="also require the recorded source SHA-256 (used for the committed snapshot)",
    )
    args = parser.parse_args()
    errors = validate(args.contract, require_pinned=args.require_pinned)
    if errors:
        for error in errors:
            print(f"CONTRACT_MISMATCH: {error}", file=sys.stderr)
        return 1
    print(f"FINANCIAL_SERVICE_CONTRACT=PASS path={args.contract}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
