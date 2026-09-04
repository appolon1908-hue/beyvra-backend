#!/usr/bin/env python3
"""Verify Beyvra read-only edge headers, readiness, and method policy."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
DISABLED_SAFETY_KEYS = (
    "simulation_enabled",
    "live_trading_enabled",
    "real_trading_enabled",
    "real_money_enabled",
    "real_deposits_enabled",
    "real_withdrawals_enabled",
    "real_internal_transfers_enabled",
    "external_execution_enabled",
    "live_broker_routing_enabled",
    "fix_live_session_enabled",
    "payments_enabled",
    "transactional_email_enabled",
    "welcome_email_enabled",
    "legacy_realtime_fallback_enabled",
)


def call(
    base_url: str,
    path: str,
    timeout: int,
    *,
    method: str = "GET",
    body: object | None = None,
) -> tuple[int, dict[str, str], object]:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "beyvra-edge-policy-verifier/1",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(
        base_url.rstrip("/") + path,
        method=method,
        headers=headers,
        data=data,
    )
    try:
        response = urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        raw, status, response_headers = (
            response.read(1_048_576),
            response.status,
            response.headers,
        )
    except HTTPError as exc:
        raw, status, response_headers = exc.read(1_048_576), exc.code, exc.headers
    try:
        payload = json.loads(raw.decode()) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    return (
        status,
        {key.lower(): value for key, value in response_headers.items()},
        payload,
    )


def add_check(
    checks: list[dict[str, object]],
    name: str,
    passed: bool,
    *,
    status: int | None = None,
    method: str | None = None,
    path: str | None = None,
) -> None:
    check: dict[str, object] = {
        "name": name,
        "result": "PASS" if passed else "FAIL",
    }
    if status is not None:
        check["http_status"] = status
    if method is not None:
        check["method"] = method
    if path is not None:
        check["path"] = path
    checks.append(check)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    checks: list[dict[str, object]] = []

    ready_status, _, ready = call(
        args.base_url,
        "/health/ready",
        args.timeout,
    )
    ready_checks = ready.get("checks", {}) if isinstance(ready, dict) else {}
    ready_ok = (
        ready_status == 200
        and isinstance(ready, dict)
        and ready.get("status") == "ready"
        and isinstance(ready_checks, dict)
        and ready_checks.get("postgresql") is True
        and ready_checks.get("postgresql_read_only") is True
        and ready_checks.get("redis") is True
        and ready_checks.get("nats") == "not_required_read_only"
    )
    add_check(
        checks,
        "readiness_and_database_read_only",
        ready_ok,
        status=ready_status,
        path="/health/ready",
    )

    version_status, headers, version = call(
        args.base_url,
        "/api/v1/system/version",
        args.timeout,
    )
    safety = version.get("safety", {}) if isinstance(version, dict) else {}
    version_ok = (
        version_status == 200
        and isinstance(version, dict)
        and version.get("source_sha") == args.source_sha
        and version.get("image_digest") == args.image_digest
        and version.get("immutable_identity_verified") is True
        and version.get("deployment_read_only") is True
        and version.get("database_read_only_enforced") is True
        and version.get("effect_flags_disabled") is True
        and version.get("read_only_certified") is True
        and isinstance(safety, dict)
        and safety.get("deployment_read_only") is True
        and all(safety.get(key) is False for key in DISABLED_SAFETY_KEYS)
    )
    add_check(
        checks,
        "exact_identity_and_complete_safety_state",
        version_ok,
        status=version_status,
        path="/api/v1/system/version",
    )

    csp = headers.get("content-security-policy", "")
    headers_ok = (
        headers.get("x-content-type-options", "").lower() == "nosniff"
        and "frame-ancestors 'none'" in csp
        and "default-src 'none'" in csp
        and bool(headers.get("referrer-policy"))
        and bool(headers.get("permissions-policy"))
        and "no-store" in headers.get("cache-control", "")
    )
    if urlsplit(args.base_url).scheme == "https":
        headers_ok = headers_ok and bool(headers.get("strict-transport-security"))
    add_check(
        checks,
        "security_headers",
        headers_ok,
        status=version_status,
        path="/api/v1/system/version",
    )

    metrics_status, _, _ = call(args.base_url, "/metrics", args.timeout)
    add_check(
        checks,
        "public_metrics_denied",
        metrics_status == 404,
        status=metrics_status,
        path="/metrics",
    )

    for method in UNSAFE_METHODS:
        status, _, payload = call(
            args.base_url,
            "/api/v1/trading/orders",
            args.timeout,
            method=method,
            body={},
        )
        blocked = (
            status == 503
            and isinstance(payload, dict)
            and isinstance(payload.get("error"), dict)
            and payload["error"].get("code") == "DEPLOYMENT_READ_ONLY"
        )
        add_check(
            checks,
            f"unsafe_method_blocked:{method}",
            blocked,
            status=status,
            method=method,
            path="/api/v1/trading/orders",
        )

    overall = all(check["result"] == "PASS" for check in checks)
    evidence = {
        "schema_version": 1,
        "target": args.base_url,
        "expected_source_sha": args.source_sha,
        "expected_image_digest": args.image_digest,
        "checks": checks,
        "overall": "PASS" if overall else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0 if overall else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (URLError, TimeoutError, OSError) as exc:
        print(
            json.dumps(
                {
                    "overall": "FAIL",
                    "failure_category": type(exc).__name__,
                }
            )
        )
        raise SystemExit(1)
