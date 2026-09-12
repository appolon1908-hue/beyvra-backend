#!/usr/bin/env python3
"""Validate checked-in OpenAPI identities and document-local references."""

import argparse
from pathlib import Path
import re
from urllib.parse import unquote

import yaml


ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

# Single source of truth for the checked-in contract surface. CI and
# scripts/production_gate.py both invoke this script with no arguments, so a
# spec added under these paths is covered everywhere without touching either.
CANONICAL_SPEC_GLOBS = ("contracts/openapi/*.yaml",)
PINNED_FINANCIAL_SPEC = ROOT / "contracts/financial-service/v1/openapi.yaml"


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


def validate_document(document, *, require_operation_ids=True):
    if not isinstance(document, dict) or not isinstance(document.get("openapi"), str):
        raise ValueError("not an OpenAPI document")
    if not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI paths must be a mapping")
    operation_ids = set()
    if any(
        tag.get("name", "").casefold() == "demo"
        for tag in document.get("tags", [])
        if isinstance(tag, dict)
    ):
        raise ValueError("retired Demo tag")
    for path, item in document["paths"].items():
        if path.rstrip("/") == "/api/v1/demo" or path.startswith("/api/v1/demo/"):
            raise ValueError("retired Demo namespace")
        if path.startswith("/api/admin/v1/accounts/") and path.rstrip("/").endswith(
            ("/demo-credit", "/demo-reset")
        ):
            raise ValueError("retired Demo administration command")
        if path.startswith("/api/v1/") and set(path.casefold().split("/")) & {
            "polygon",
            "massive",
            "twelve-data",
            "coingecko",
            "alpaca",
            "stripe",
            "binance-pay",
            "bitgo",
            "newsdata",
        }:
            raise ValueError("provider-specific customer path")
        if not isinstance(item, dict):
            raise ValueError(f"invalid path item: {path}")
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                raise ValueError(f"invalid operation: {method} {path}")
            if any(str(tag).casefold() == "demo" for tag in operation.get("tags", [])):
                raise ValueError("retired Demo tag")
            if method in {"patch", "put", "post"} and re.fullmatch(
                r"/api/v1/wallets?/[^/]+/(?:balance|credit)/?", path
            ):
                raise ValueError("direct financial balance mutation")
            operation_id = operation.get("operationId")
            if operation_id is None:
                if require_operation_ids:
                    raise ValueError(f"missing operationId: {method} {path}")
                continue
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise ValueError(f"invalid operationId: {method} {path}")
            if operation_id in {
                "createDemoSession",
                "previewDemoOrder",
                "createDemoOrder",
                "listDemoOrders",
                "getDemoOrder",
                "cancelDemoOrder",
                "listDemoTrades",
                "getDemoWallet",
                "refillDemoWallet",
                "adminDemoCredit",
                "adminDemoReset",
            }:
                raise ValueError("retired Demo operationId")
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


def validate_file(path, *, semantic=False):
    with open(path, encoding="utf-8") as source:
        document = yaml.load(source, Loader=UniqueKeyLoader)
    pinned_dependency = path.resolve() == PINNED_FINANCIAL_SPEC.resolve()
    if pinned_dependency:
        from validate_financial_service_contract import validate

        failures = validate(path, require_pinned=True)
        if failures:
            raise ValueError(
                "pinned Financial Service contract failed: " + "; ".join(failures)
            )
    # Upstream operation IDs are optional in OpenAPI. A consumer must not edit
    # a certified vendor snapshot to invent IDs or silently update its digest.
    validate_document(document, require_operation_ids=not pinned_dependency)
    if semantic:
        from openapi_spec_validator import validate

        validate(document)


def main(paths, *, semantic=False):
    # An empty argv means "validate the whole contract surface", never
    # "validate nothing" -- reporting success without opening a file would
    # let a broken spec reach production behind a green check.
    documents = [Path(path) for path in paths] or canonical_specs()
    if not documents:
        raise SystemExit(
            "no OpenAPI documents found; refusing to report success vacuously"
        )
    if not paths:
        documents.append(PINNED_FINANCIAL_SPEC)
    for path in documents:
        validate_file(path, semantic=semantic)
        print(f"OPENAPI_VALID={path}")
    print(f"OPENAPI_DOCUMENTS_VALIDATED={len(documents)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Also validate the full OpenAPI specification schema",
    )
    arguments = parser.parse_args()
    main(arguments.paths, semantic=arguments.semantic)
