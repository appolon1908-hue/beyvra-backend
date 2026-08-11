#!/usr/bin/env python3
"""Non-destructive staging API verifier.

Uses an optional pre-provisioned synthetic token. Without one it creates a
short-lived guest-demo session and restricts itself to read/fail-closed probes.
Tokens and response bodies are never written to evidence.
"""

import argparse
import json
import os
import ssl
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SAFE_ERROR_FORBIDDEN = ("request_id", "correlation_id", "traceback", "stack", "exception", "sql", "internal_service")


def call(base, method, path, *, token=None, body=None, idempotency=None, timeout=15):
    headers = {"Accept": "application/json", "User-Agent": "beyvra-staging-certifier/1"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    request = Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=timeout, context=ssl.create_default_context())
        raw, status = response.read(1_048_576), response.status
    except HTTPError as exc:
        raw, status = exc.read(1_048_576), exc.code
    payload = json.loads(raw.decode()) if raw else {}
    return status, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("BEYVRA_STAGING_BASE_URL", "https://staging.beyvra.com"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if "staging" not in args.base_url.lower() and os.getenv("ALLOW_NON_STAGING_CERTIFICATION") != "yes":
        raise SystemExit("Refusing a non-staging target")

    token = os.getenv("BEYVRA_STAGING_ACCESS_TOKEN", "").strip()
    principal = "preprovisioned_synthetic"
    if not token:
        principal = "guest_demo"
        status, payload = call(args.base_url, "POST", "/api/v1/demo/sessions", body={}, idempotency=f"api-cert-{uuid.uuid4()}")
        if status != 201 or not payload.get("access"):
            raise SystemExit(f"Unable to create guest demo session: HTTP {status}")
        token = payload["access"]

    probes = [
        ("GET", "/health/live", None, {200}),
        ("GET", "/health/ready", None, {200}),
        ("GET", "/api/v1/status", None, {200}),
        ("GET", "/api/v1/features", None, {200}),
        ("GET", "/api/v1/me", None, {200}),
        ("GET", "/api/v1/account", None, {200}),
        ("GET", "/api/v1/account/sessions", None, {200}),
        ("GET", "/api/v1/account/security-events", None, {200}),
        ("GET", "/api/v1/compliance/profile", None, {200, 409}),
        ("GET", "/api/v1/compliance/requirements", None, {200, 409}),
        ("GET", "/api/v1/compliance/restrictions", None, {200}),
        ("GET", "/api/v1/market/instruments", None, {200}),
        ("GET", "/api/v1/demo/account", None, {200}),
        ("GET", "/api/v1/demo/wallets", None, {200}),
        ("GET", "/api/v1/demo/orders", None, {200, 405}),
        ("GET", "/api/v1/demo/trades", None, {200}),
        ("GET", "/api/v1/demo/positions", None, {200}),
        ("GET", "/api/v1/notifications", None, {200}),
        ("GET", "/api/v1/reports/activity", None, {200}),
        ("GET", "/api/v1/reports/transactions", None, {200}),
        ("GET", "/api/v1/privacy/requests", None, {200}),
        ("GET", "/api/v1/wallets", None, {503}),
        ("POST", "/api/v1/deposits", {}, {503}),
        ("POST", "/api/v1/withdrawals", {}, {503}),
        ("POST", "/api/v1/transfers", {}, {503}),
        ("POST", "/api/v1/trading/orders", {}, {503}),
    ]
    results, failed = [], False
    for method, path, body, allowed in probes:
        try:
            status, payload = call(args.base_url, method, path, token=token, body=body)
            serialized = json.dumps(payload).lower()
            safe = not any(term in serialized for term in SAFE_ERROR_FORBIDDEN)
            schema_valid = isinstance(payload, dict)
            passed = status in allowed and schema_valid and safe
            error_code = payload.get("error", {}).get("code") if isinstance(payload.get("error"), dict) else payload.get("code")
            results.append({"method": method, "path": path, "http_status": status, "schema_valid": schema_valid, "safe_error": safe, "error_code": error_code, "result": "PASS" if passed else "FAIL"})
            failed = failed or not passed
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            results.append({"method": method, "path": path, "result": "FAIL", "failure_category": type(exc).__name__})
            failed = True

    anonymous_status, anonymous_payload = call(args.base_url, "GET", "/api/v1/account")
    anonymous_ok = anonymous_status == 401 and anonymous_payload.get("error", {}).get("code") == "AUTHENTICATION_REQUIRED"
    evidence = {"schema_version": 1, "target": args.base_url, "principal": principal, "probe_count": len(results) + 1, "anonymous_auth_result": "PASS" if anonymous_ok else "FAIL", "results": results, "overall": "PASS" if not failed and anonymous_ok else "FAIL"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return 0 if evidence["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
