#!/usr/bin/env python3
"""Validate one reviewed Beyvra release intent and emit GitHub outputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED_KEYS = {
    "schema_version",
    "enabled",
    "source_sha",
    "target",
    "publish_images",
    "backend_image",
    "edge_image",
    "deploy",
    "change_id",
    "allow_schema_migrations",
    "migration_compatibility_approved",
}
DIGEST = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
CHANGE = re.compile(r"^[A-Za-z0-9._-]+$")


def emit(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: validate_release_intent.py INTENT GREEN_SHA OUTPUT")
    intent_path, green_sha, output_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    if not SHA.fullmatch(green_sha):
        raise SystemExit("green main SHA is invalid")
    if not intent_path.is_file():
        emit(output_path, {"enabled": "false"})
        return 0

    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if not isinstance(intent, dict) or set(intent) - ALLOWED_KEYS:
        raise SystemExit("release intent contains unsupported fields")
    if intent.get("schema_version") != 1:
        raise SystemExit("unsupported release-intent schema")
    if intent.get("enabled") is not True:
        emit(output_path, {"enabled": "false"})
        return 0

    target = intent.get("target")
    publish = intent.get("publish_images")
    deploy = intent.get("deploy")
    migrations = intent.get("allow_schema_migrations")
    migration_approved = intent.get("migration_compatibility_approved")
    for name, value in {
        "publish_images": publish,
        "deploy": deploy,
        "allow_schema_migrations": migrations,
        "migration_compatibility_approved": migration_approved,
    }.items():
        if not isinstance(value, bool):
            raise SystemExit(f"{name} must be boolean")
    if migrations or migration_approved:
        raise SystemExit("read-only release intents cannot authorize schema migrations")

    change_id = str(intent.get("change_id", ""))
    if not CHANGE.fullmatch(change_id):
        raise SystemExit("invalid change_id")
    requested_source = str(intent.get("source_sha", ""))
    backend_image = str(intent.get("backend_image", ""))
    edge_image = str(intent.get("edge_image", ""))

    if target == "staging-readonly":
        if requested_source != "CURRENT_MAIN" or publish is not True or deploy is not True:
            raise SystemExit("staging must build and deploy CURRENT_MAIN")
        if backend_image or edge_image:
            raise SystemExit("staging must not supply pre-existing image digests")
        source_sha = green_sha
    elif target == "production-readonly":
        if not SHA.fullmatch(requested_source) or publish is not False or deploy is not True:
            raise SystemExit("production must reuse an exact staging-certified source")
        if not DIGEST.fullmatch(backend_image) or not DIGEST.fullmatch(edge_image):
            raise SystemExit("production images must be immutable digests")
        source_sha = requested_source
    else:
        raise SystemExit("unsupported deployment target")

    emit(
        output_path,
        {
            "enabled": "true",
            "source_sha": source_sha,
            "target": target,
            "publish_images": str(publish).lower(),
            "backend_image": backend_image,
            "edge_image": edge_image,
            "deploy": "true",
            "change_id": change_id,
            "allow_schema_migrations": "false",
            "migration_compatibility_approved": "false",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
