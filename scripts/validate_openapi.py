#!/usr/bin/env python3
"""Parse OpenAPI YAML while rejecting duplicate mapping keys."""

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]

# Single source of truth for the checked-in contract surface. CI and
# scripts/production_gate.py both invoke this script with no arguments, so a
# spec added under these paths is covered everywhere without touching either.
CANONICAL_SPEC_GLOBS = (
    "contracts/openapi/*.yaml",
    "contracts/financial-service/v1/openapi.yaml",
    "FX/openapi.platform-ops.yaml",
)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping,
)


def canonical_specs():
    discovered = []
    for pattern in CANONICAL_SPEC_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path not in discovered:
                discovered.append(path)
    return discovered


def main(paths):
    # An empty argv means "validate the whole contract surface", never
    # "validate nothing" -- reporting success without reading a file would
    # let a broken spec reach production behind a green check.
    documents = [Path(path) for path in paths] or canonical_specs()
    if not documents:
        raise SystemExit(
            "no OpenAPI documents found; refusing to report success vacuously"
        )
    for path in documents:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        if document.get("openapi") is None or document.get("paths") is None:
            raise ValueError(f"not an OpenAPI document: {path}")
        print(f"OPENAPI_VALID={path}")
    print(f"OPENAPI_DOCUMENTS_VALIDATED={len(documents)}")


if __name__ == "__main__":
    main(sys.argv[1:])
