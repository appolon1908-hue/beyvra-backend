#!/usr/bin/env python3
"""Verify a public Beyvra read-only candidate without performing mutations."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch_json(
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
        "User-Agent": "beyvra-release-verifier/2",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    request = Request(
        base_url.rstrip("/") + path,
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
        response_body, status = response.read(1_048_576), response.status
    except HTTPError as exc:
        response_body, status = exc.read(1_048_576), exc.code

    try:
        return (
            status,
            json.loads(response_body.decode()) if response_body else {},
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    checks: list[dict[str, object]] = []

    for path, expected_status in (
        ("/health/live", "live"),
        ("/health/ready", "ready"),
    ):
        status, payload = fetch_json(
            args.base_url,
            path,
            args.timeout,
        )
        passed = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("status") == expected_status
        )
        checks.append(
            {
                "path": path,
                "http_status": status,
                "result": "PASS" if passed else "FAIL",
            }
        )

    version_status, version = fetch_json(
        args.base_url,
        "/api/v1/system/version",
        args.timeout,
    )
    version_passed = (
        version_status == 200
        and isinstance(version, dict)
        and version.get("source_sha") == args.source_sha
        and version.get("image_digest") == args.image_digest
        and version.get("immutable_identity_verified") is True
    )
    safety = version.get("safety", {}) if isinstance(version, dict) else {}
    safety_passed = (
        isinstance(safety, dict)
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
            "http_status": version_status,
            "identity_match": version_passed,
            "safety_match": safety_passed,
            "result": (
                "PASS" if version_passed and safety_passed else "FAIL"
            ),
        }
    )

    capability_status, capabilities = fetch_json(
        args.base_url,
        "/api/v1/system/capabilities",
        args.timeout,
    )
    capabilities_passed = (
        capability_status == 200
        and isinstance(capabilities, dict)
        and capabilities.get("deployment_read_only") is True
        and capabilities.get("simulation") is False
        and capabilities.get("real_trading") is False
        and capabilities.get("real_money") is False
    )
    checks.append(
        {
            "path": "/api/v1/system/capabilities",
            "http_status": capability_status,
            "result": "PASS" if capabilities_passed else "FAIL",
        }
    )

    mutation_status, mutation_payload = fetch_json(
        args.base_url,
        "/api/v1/trading/orders",
        args.timeout,
        method="POST",
        body={},
    )
    mutation_blocked = (
        mutation_status == 503
        and isinstance(mutation_payload, dict)
        and isinstance(mutation_payload.get("error"), dict)
        and mutation_payload["error"].get("code")
        == "DEPLOYMENT_READ_ONLY"
    )
    checks.append(
        {
            "path": "/api/v1/trading/orders",
            "method": "POST",
            "http_status": mutation_status,
            "result": "PASS" if mutation_blocked else "FAIL",
        }
    )

    overall = all(check["result"] == "PASS" for check in checks)
    evidence = {
        "schema_version": 2,
        "target": args.base_url,
        "expected_source_sha": args.source_sha,
        "expected_image_digest": args.image_digest,
        "checks": checks,
        "overall": "PASS" if overall else "FAIL",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0 if overall else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (URLError, TimeoutError, OSError) as exc:
        print(
            json.dumps(
                {
                    "overall": "FAIL",
                    "failure_category": type(exc).__name__,
                }
            )
        )
        sys.exit(1)
