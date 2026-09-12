#!/usr/bin/env python3
"""Validate checked-in OpenAPI identities and document-local references."""

from pathlib import Path
import sys
from urllib.parse import unquote

import yaml


ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

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


def validate_document(document):
    if not isinstance(document, dict) or not isinstance(document.get("openapi"), str):
        raise ValueError("not an OpenAPI document")
    if not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI paths must be a mapping")
    operation_ids = set()
    for path, item in document["paths"].items():
        if not isinstance(item, dict):
            raise ValueError(f"invalid path item: {path}")
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                raise ValueError(f"invalid operation: {method} {path}")
            operation_id = operation.get("operationId")
            # Some existing auxiliary contracts omit IDs. The migration audit
            # records those gaps; supplied IDs must already be valid and unique.
            if operation_id is None:
                continue
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise ValueError(f"invalid operationId: {method} {path}")
            if operation_id in operation_ids:
                raise ValueError(f"duplicate operationId: {operation_id}")
            operation_ids.add(operation_id)

    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                reference = value["$ref"]
                if not isinstance(reference, str):
                    raise ValueError("$ref must be a string")
                if reference.startswith("#"):
                    fragment = unquote(reference[1:])
                    if fragment and not fragment.startswith("/"):
                        raise ValueError("document-local $ref must use a JSON pointer")
                    target = document
                    try:
                        for token in fragment[1:].split("/") if fragment else ():
                            token = token.replace("~1", "/").replace("~0", "~")
                            if isinstance(target, list):
                                if not token.isdecimal() or (
                                    len(token) > 1 and token[0] == "0"
                                ):
                                    raise ValueError("invalid array index")
                                target = target[int(token)]
                            else:
                                target = target[token]
                    except (KeyError, IndexError, TypeError, ValueError) as error:
                        raise ValueError(
                            f"unresolved local $ref: {reference}"
                        ) from error
                else:
                    # Validation never fetches remote resources. Fail explicitly
                    # until a repository-local multi-document resolver is added.
                    raise ValueError("external $ref is unsupported by this validator")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)


def main(paths):
    # An empty argv means "validate the whole contract surface", never
    # "validate nothing" -- reporting success without opening a file would
    # let a broken spec reach production behind a green check.
    documents = [Path(path) for path in paths] or canonical_specs()
    if not documents:
        raise SystemExit(
            "no OpenAPI documents found; refusing to report success vacuously"
        )
    for path in documents:
        with open(path, encoding="utf-8") as source:
            document = yaml.load(source, Loader=UniqueKeyLoader)
        validate_document(document)
        print(f"OPENAPI_VALID={path}")
    print(f"OPENAPI_DOCUMENTS_VALIDATED={len(documents)}")


if __name__ == "__main__":
    main(sys.argv[1:])
