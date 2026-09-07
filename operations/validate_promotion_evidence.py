#!/usr/bin/env python3
"""Validate the non-secret production promotion manifest contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    value = json.loads(args.manifest.read_text())
    required = {
        "schema_version": 1,
        "target": "staging-readonly",
        "certification_result": "PASS",
        "rollback_rehearsal": "PASS",
        "zero_live_effects": "PASS",
        "deployment_read_only": True,
        "live_trading_authorized": False,
        "real_money_authorized": False,
        "payments_authorized": False,
        "withdrawals_authorized": False,
        "transactional_email_authorized": False,
        "external_execution_authorized": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise SystemExit(f"invalid {key}: {value.get(key)!r}")

    if not SHA.fullmatch(str(value.get("source_sha", ""))):
        raise SystemExit("source_sha is not exact")
    for key in ("backend_image", "edge_image"):
        if not IMAGE.fullmatch(str(value.get(key, ""))):
            raise SystemExit(f"{key} is not an immutable GHCR digest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
