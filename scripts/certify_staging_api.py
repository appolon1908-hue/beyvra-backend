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


SAFE_ERROR_FORBIDDEN = (
    "traceback",
    "stack",
    "exception",
    "sql",
    "internal_service",
)


def call(
    base,
    method,
    path,
    *,
    token=None,
    body=None,
    idempotency=None,
    timeout=15,
):
    headers = {
        "Accept": "application/json",
        "User-Agent": "beyvra-staging-certifier/2",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
        headers["X-Request-ID"] = str(uuid.uuid4())
    request = Request(
        base.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        raw, status = response.read(1_048_576), response.status
    except HTTPError as exc:
        raw, status = exc.read(1_048_576), exc.code

    try:
        payload = json.loads(raw.decode()) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    return status, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "BEYVRA_STAGING_BASE_URL",
            "https://staging.beyvra.com",
        ),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if (
        "staging" not in args.base_url.lower()
        and os.getenv("ALLOW_NON_STAGING_CERTIFICATION") != "yes"
    ):
        raise SystemExit("Refusing a non-staging target")

    token = os.getenv("BEYVRA_STAGING_ACCESS_TOKEN", "").strip()
    principal = "preprovisioned_synthetic"
    if not token:
        principal = "guest_demo"
        status, payload = call(
            args.base_url,
            "POST",
            "/api/v1/demo/sessions",
            body={},
            idempotency=f"api-cert-{uuid.uuid4()}",
        )
        if (
            status != 201
            or not isinstance(payload, dict)
            or not payload.get("access")
        ):
            raise SystemExit(
                f"Unable to create guest demo session: HTTP {status}"
            )
        token = payload["access"]

    probes = [
        ("GET", "/health/live", None, {200}),
        ("GET", "/health/ready", None, {200}),
        ("GET", "/api/v1/system/status", None, {200}),
        ("GET", "/api/v1/system/capabilities", None, {200}),
        ("GET", "/api/v1/system/version", None, {200}),
        ("GET", "/api/v1/features/", None, {200}),
        ("GET", "/api/v1/me/", None, {200}),
        ("GET", "/api/v1/tenant/context", None, {200}),
        ("GET", "/api/v1/security/sessions", None, {200}),
        ("GET", "/api/v1/compliance/profile", None, {200, 409}),
        ("GET", "/api/v1/compliance/requirements", None, {200, 409}),
        ("GET", "/api/v1/market/instruments", None, {200}),
        ("GET", "/api/v1/trading/accounts", None, {200}),
        ("GET", "/api/v1/trading/portfolio", None, {200}),
        ("GET", "/api/v1/trading/orders", None, {200}),
        ("GET", "/api/v1/trading/positions", None, {200}),
        ("GET", "/api/v1/notifications/", None, {200}),
        ("GET", "/api/v1/reports/activity", None, {200}),
        ("GET", "/api/v1/reports/transactions", None, {200}),
        ("GET", "/api/v1/privacy/deletion-requests", None, {200}),
        ("GET", "/api/v1/wallets/", None, {503}),
        ("POST", "/api/v1/deposits/", {}, {503}),
        ("POST", "/api/v1/withdrawals/", {}, {503}),
        ("POST", "/api/v1/transfers/", {}, {503}),
        ("POST", "/api/v1/trading/orders", {}, {503}),
    ]
    results, failed = [], False
    for method, path, body, allowed in probes:
        try:
            idempotency = (
                f"api-cert-{uuid.uuid4()}" if method != "GET" else None
            )
            status, payload = call(
                args.base_url,
                method,
                path,
                token=token,
                body=body,
                idempotency=idempotency,
            )
            serialized = (
                json.dumps(payload).lower() if payload is not None else ""
            )
            safe = not any(term in serialized for term in SAFE_ERROR_FORBIDDEN)
            schema_valid = isinstance(payload, (dict, list))
            passed = status in allowed and schema_valid and safe
            error_code = None
            if isinstance(payload, dict):
                error = payload.get("error")
                error_code = (
                    error.get("code")
                    if isinstance(error, dict)
                    else payload.get("code")
                )
            results.append(
                {
                    "method": method,
                    "path": path,
                    "http_status": status,
                    "schema_valid": schema_valid,
                    "safe_error": safe,
                    "error_code": error_code,
                    "result": "PASS" if passed else "FAIL",
                }
            )
            failed = failed or not passed
        except (URLError, TimeoutError, ValueError) as exc:
            results.append(
                {
                    "method": method,
                    "path": path,
                    "result": "FAIL",
                    "failure_category": type(exc).__name__,
                }
            )
            failed = True

    anonymous_status, anonymous_payload = call(
        args.base_url,
        "GET",
        "/api/v1/trading/accounts",
    )
    anonymous_ok = (
        anonymous_status == 401
        and isinstance(anonymous_payload, dict)
        and isinstance(anonymous_payload.get("error"), dict)
        and anonymous_payload["error"].get("code")
        == "AUTHENTICATION_REQUIRED"
    )
    evidence = {
        "schema_version": 2,
        "target": args.base_url,
        "principal": principal,
        "probe_count": len(results) + 1,
        "anonymous_auth_result": "PASS" if anonymous_ok else "FAIL",
        "results": results,
        "overall": "PASS" if not failed and anonymous_ok else "FAIL",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return 0 if evidence["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
