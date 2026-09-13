#!/usr/bin/env python3
"""Generate an auditable operation inventory without inferring implementation.

Ordinary generation exposes missing evidence. --certify rejects it; a route or
FEATURE_DISABLED response alone is never evidence of an implemented service.
"""

import argparse
import hashlib
import json
import re
from urllib.parse import urlsplit

import yaml

from validate_openapi import HTTP_METHODS, ROOT, UniqueKeyLoader, canonical_specs


STATUSES = frozenset({"IMPLEMENTED", "IMPLEMENTED_GATED", "REMOVED"})
FIELDS = (
    "operation_id",
    "method",
    "path",
    "backend_module",
    "service",
    "authorization",
    "feature_gate",
    "test_file",
    "frontend_caller",
    "implementation_status",
)
MANIFEST = ROOT / "contracts/implementation-evidence.json"
OUTPUT = ROOT / "docs/API-IMPLEMENTATION-MATRIX.md"


def endpoint_paths(document, item, operation, path):
    servers = operation.get(
        "servers", item.get("servers", document.get("servers", [{"url": "/"}]))
    )
    result = set()
    for server in servers:
        url = server["url"]
        for name, variable in server.get("variables", {}).items():
            url = url.replace("{" + name + "}", str(variable["default"]))
        if "{" in url or "}" in url:
            raise ValueError("unresolved server URL variable")
        prefix = urlsplit(url).path.rstrip("/")
        result.add(prefix + path)
    return sorted(result)


def inventory(paths, root=ROOT):
    rows = {}
    missing_ids = []
    for source in paths:
        document = yaml.load(source.read_text(), Loader=UniqueKeyLoader)
        for path, item in document["paths"].items():
            for method, operation in item.items():
                if method not in HTTP_METHODS:
                    continue
                endpoints = endpoint_paths(document, item, operation, path)
                operation_id = operation.get("operationId")
                if not isinstance(operation_id, str) or not operation_id.strip():
                    missing_ids.append(
                        (str(source.relative_to(root)), method.upper(), endpoints)
                    )
                    continue
                identity = (method.upper(), tuple(endpoints))
                previous = rows.get(operation_id)
                if previous and previous["identity"] != identity:
                    raise ValueError(f"conflicting operationId: {operation_id}")
                if previous:
                    previous["sources"].add(str(source.relative_to(root)))
                    continue
                rows[operation_id] = {
                    "identity": identity,
                    "operation_id": operation_id,
                    "method": method.upper(),
                    "path": ", ".join(endpoints),
                    "sources": {str(source.relative_to(root))},
                }
    return rows, sorted(missing_ids)


def verify_evidence(rows, evidence, root=ROOT):
    unknown = set(evidence) - set(rows)
    if unknown:
        raise ValueError(
            "evidence references unknown operations: " + ", ".join(sorted(unknown))
        )
    for operation_id, record in evidence.items():
        row = rows[operation_id]
        if record.get("implementation_status") not in STATUSES:
            raise ValueError(f"invalid implementation status: {operation_id}")
        for field in FIELDS[1:]:
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"missing evidence field {field}: {operation_id}")
        if (record["method"], record["path"]) != (row["method"], row["path"]):
            raise ValueError(f"evidence endpoint changed: {operation_id}")
        files = record.get("file_sha256")
        if not isinstance(files, dict) or not files:
            raise ValueError(f"missing source bindings: {operation_id}")
        for name, binding in files.items():
            if not isinstance(binding, dict) or set(binding) != {"sha256"}:
                raise ValueError(f"invalid source binding: {operation_id}")
            expected = binding["sha256"]
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"invalid evidence file: {operation_id}")
            if not isinstance(expected, str) or not re.fullmatch(
                r"[0-9a-f]{64}", expected
            ):
                raise ValueError(f"invalid source digest: {operation_id}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"stale source evidence: {operation_id}: {name}")
        # Evidence has to bind the handler, underlying service, and tests; prose
        # describing an adapter is insufficient. Frontend evidence is recorded
        # separately because it belongs to another repository/release SHA.
        for field in ("backend_module", "service", "test_file"):
            if record[field].split("::", 1)[0] not in files:
                raise ValueError(f"unbound {field}: {operation_id}")
        if record["implementation_status"] == "IMPLEMENTED_GATED":
            if record["feature_gate"] == "NONE" or not record.get("adapter_test"):
                raise ValueError(
                    f"gated implementation requires adapter evidence: {operation_id}"
                )
            if record["adapter_test"].split("::", 1)[0] not in files:
                raise ValueError(f"unbound adapter test: {operation_id}")
        row.update({field: record[field] for field in FIELDS[3:]})


def cell(value):
    return str(value).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def render(rows, missing_ids):
    unresolved = sum("implementation_status" not in row for row in rows.values())
    lines = [
        "# API implementation matrix",
        "",
        "Generated by `python3 scripts/generate_api_implementation_matrix.py`. Do not edit by hand.",
        "",
        f"Operations: **{len(rows)}**. Missing implementation evidence: **{unresolved}**. "
        f"Contract operations missing operationId: **{len(missing_ids)}**.",
        "",
        "This is an incomplete migration inventory, not release certification. Empty cells mean "
        "evidence is absent; no implementation status is assigned. Existing contracts include "
        "compatibility APIs awaiting migration to the revised written mission. Duplicate snapshots "
        "of the same operation are counted once after resolving server base paths.",
        "The separately pinned Financial Service dependency remains byte-for-byte upstream data "
        "and is validated independently; the consumer does not assign its missing operation IDs.",
        "",
        "Only reviewed, source-bound records in `contracts/implementation-evidence.json` can assign "
        "IMPLEMENTED, IMPLEMENTED_GATED or REMOVED. A resolved route, a generic response or a feature "
        "gate is insufficient. `--certify` rejects every unresolved row and missing operationId; "
        "it supplements the runtime, frontend, provider and staging tests required by B19.",
        "",
        "| " + " | ".join(FIELDS) + " |",
        "| " + " | ".join("---" for _ in FIELDS) + " |",
    ]
    for operation_id in sorted(rows):
        row = rows[operation_id]
        lines.append(
            "| " + " | ".join(cell(row.get(field, "")) for field in FIELDS) + " |"
        )
    lines.extend(["", "## Source documents", ""])
    sources = sorted({source for row in rows.values() for source in row["sources"]})
    lines.extend(f"- `{source}`" for source in sources)
    if missing_ids:
        lines.extend(["", "## Operations missing operationId", ""])
        for source, method, paths in missing_ids:
            lines.append(f"- `{source}`: {method} {', '.join(paths)}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Reject a stale generated matrix"
    )
    parser.add_argument(
        "--certify", action="store_true", help="Reject missing implementation evidence"
    )
    args = parser.parse_args()
    rows, missing_ids = inventory(canonical_specs())
    if not rows:
        raise SystemExit("No operations discovered; refusing empty certification")
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema_version") != 1:
        raise SystemExit("Unsupported implementation evidence schema")
    verify_evidence(rows, manifest["operations"])
    result = render(rows, missing_ids)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != result:
            raise SystemExit("API implementation matrix is stale; regenerate it")
    else:
        OUTPUT.write_text(result)
    unresolved = sum("implementation_status" not in row for row in rows.values())
    if args.certify and (unresolved or missing_ids):
        raise SystemExit(
            f"Certification refused: {unresolved} unresolved operations; {len(missing_ids)} missing IDs"
        )
    print(
        f"API_MATRIX_OPERATIONS={len(rows)} UNRESOLVED={unresolved} MISSING_IDS={len(missing_ids)}"
    )


if __name__ == "__main__":
    main()
