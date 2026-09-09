#!/usr/bin/env python3
"""Create a privacy-safe cryptographic fingerprint of application tables.

Rows are streamed inside one repeatable-read, read-only transaction. The
process emits only table names, exact row counts, and order-independent
256-bit multiset accumulators; row contents never leave the process.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FX.settings")

import django  # noqa: E402


django.setup()

from django.db import connection, transaction  # noqa: E402


EXCLUDED_PREFIXES = ("django_cache",)
MODULUS = 1 << 256


def main() -> int:
    timeout_ms = int(os.getenv("FINGERPRINT_STATEMENT_TIMEOUT_MS", "1800000"))
    if timeout_ms < 1000 or timeout_ms > 3_600_000:
        raise ValueError("FINGERPRINT_STATEMENT_TIMEOUT_MS is outside policy")

    quote = connection.ops.quote_name
    rows: list[dict[str, object]] = []
    connection.ensure_connection()

    with transaction.atomic():
        with connection.cursor() as control:
            control.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            control.execute("SET LOCAL statement_timeout = %s", [timeout_ms])
            tables = sorted(
                table
                for table in connection.introspection.table_names(control)
                if not table.startswith(EXCLUDED_PREFIXES)
            )

        raw_connection = connection.connection
        if raw_connection is None:
            raise RuntimeError("database connection is unavailable")

        for index, table in enumerate(tables):
            accumulator = 0
            count = 0
            quoted = quote(table)
            cursor_name = f"beyvra_fingerprint_{index}"
            with raw_connection.cursor(name=cursor_name) as stream:
                stream.itersize = 1000
                stream.execute(f"SELECT row_to_json(t)::text FROM {quoted} AS t")
                for (serialized_row,) in stream:
                    digest = hashlib.sha256(serialized_row.encode("utf-8")).digest()
                    accumulator = (
                        accumulator + int.from_bytes(digest, "big")
                    ) % MODULUS
                    count += 1
            rows.append(
                {
                    "table": table,
                    "row_count": count,
                    "row_multiset_sha256_accumulator": f"{accumulator:064x}",
                }
            )

    canonical = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()
    result = {
        "schema_version": 2,
        "algorithm": "sha256(table,row_count,sum_mod_2^256(sha256(row_json)))",
        "transaction": "repeatable_read_read_only",
        "table_count": len(rows),
        "database_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "tables": rows,
    }
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - sanitized operational boundary
        print(
            json.dumps(
                {
                    "overall": "FAIL",
                    "failure_category": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
