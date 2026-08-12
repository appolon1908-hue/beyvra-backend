#!/usr/bin/env python3
"""Validate that every canonical publisher domain has checked-in stream coverage."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "FX/apps/foundation/publisher.py"
BOOTSTRAP = ROOT / "infra/realtime-v2/bootstrap-streams.sh"


def publisher_domains() -> set[str]:
    tree = ast.parse(PUBLISHER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CANONICAL_SUBJECT_DOMAINS"
            for target in node.targets
        ):
            return {item.value for item in node.value.elts if isinstance(item, ast.Constant)}
    raise RuntimeError("canonical publisher domain registry not found")


def stream_domains() -> set[str]:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    return set(re.findall(r"--subjects '([a-z_]+)\.>'", text))


def main() -> int:
    missing = publisher_domains() - stream_domains()
    if missing:
        raise SystemExit("PUBLISHED_SUBJECTS_WITHOUT_STREAM=" + ",".join(sorted(missing)))
    print("PUBLISHED_SUBJECTS_WITHOUT_STREAM=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
