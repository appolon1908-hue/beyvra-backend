#!/usr/bin/env python3
"""Verify an exact fail-closed previous release during rollback rehearsal."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call(
    base_url: str,
    path: str,
    timeout: int,
    *,
    method: str = "GET",
    body: object | None = None,
) -> tuple[int, object]:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "beyvra-rollback-verifier/1",
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
        raw, status = response.read(1_048_576), response.status
    except HTTPError as exc:
        raw, status = exc.read(1_048_576), exc.code
    try:
        payload = json.loads(raw.decode()) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    return status, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    checks: list[dict[str, object]] = []
    for path, state in (("/health/live", "live"), ("/health/ready", "ready")):
        status, payload = call(args.base_url, path, args.timeout)
        passed = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("status") == state
        )
        checks.append(
            {
                "path": path,
                "http_status": status,
                "result": "PASS" if passed else "FAIL",
            }
        )

    status, version = call(
        args.base_url,
        "/api/v1/system/version",
        args.timeout,
    )
    safety = version.get("safety", {}) if isinstance(version, dict) else {}
    identity_ok = (
        status == 200
        and isinstance(version, dict)
        and version.get("source_sha") == args.source_sha
        and version.get("image_digest") == args.image_digest
        and version.get("immutable_identity_verified") is True
        and isinstance(safety, dict)
        and safety.get("deployment_read_only") is True
        and safety.get("simulation_enabled") is False
        and safety.get("live_trading_enabled") is False
        and safety.get("real_trading_enabled") is False
        and safety.get("real_money_enabled") is False
        and safety.get("external_execution_enabled") is False
    )
    checks.append(
        {
            "path": "/api/v1/system/version",
            "http_status": status,
            "result": "PASS" if identity_ok else "FAIL",
        }
    )

    status, payload = call(
        args.base_url,
        "/api/v1/trading/orders",
        args.timeout,
        method="POST",
        body={},
    )
    mutation_ok = (
        status == 503
        and isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and payload["error"].get("code") == "DEPLOYMENT_READ_ONLY"
    )
    checks.append(
        {
            "path": "/api/v1/trading/orders",
            "method": "POST",
            "http_status": status,
            "result": "PASS" if mutation_ok else "FAIL",
        }
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
