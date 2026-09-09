"""Database-level fail-closed enforcement for read-only deployments."""

from __future__ import annotations

import os

from django.db import connections
from django.db.backends.signals import connection_created


def deployment_read_only_enabled() -> bool:
    return (
        os.getenv("DEPLOYMENT_READ_ONLY", "false").strip().lower()
        == "true"
    )


def enforce_read_only_connection(sender=None, connection=None, **_kwargs):
    """Make every PostgreSQL transaction read-only for runtime processes."""
    if (
        not deployment_read_only_enabled()
        or connection is None
        or connection.vendor != "postgresql"
    ):
        return
    with connection.cursor() as cursor:
        cursor.execute("SET default_transaction_read_only = on")


def install_read_only_enforcement() -> None:
    connection_created.connect(
        enforce_read_only_connection,
        dispatch_uid="beyvra.enforce_read_only_connection",
        weak=False,
    )
    for connection in connections.all():
        if connection.connection is not None:
            enforce_read_only_connection(connection=connection)


def database_read_only_state(connection=None) -> bool:
    if not deployment_read_only_enabled():
        return False
    connection = connection or connections["default"]
    if connection.vendor != "postgresql":
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW default_transaction_read_only")
            default_state = str(cursor.fetchone()[0]).lower()
            cursor.execute("SHOW transaction_read_only")
            transaction_state = str(cursor.fetchone()[0]).lower()
    except Exception:
        return False
    return default_state == "on" and transaction_state == "on"
