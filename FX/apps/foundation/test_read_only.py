import os
from contextlib import contextmanager
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.foundation.read_only import (
    database_read_only_state,
    enforce_read_only_connection,
)


class FakeCursor:
    def __init__(self, rows=None):
        self.statements = []
        self.rows = list(rows or [])

    def execute(self, statement):
        self.statements.append(statement)

    def fetchone(self):
        return (self.rows.pop(0),)


class FakeConnection:
    vendor = "postgresql"

    def __init__(self, rows=None):
        self.cursor_instance = FakeCursor(rows)

    @contextmanager
    def cursor(self):
        yield self.cursor_instance


class ReadOnlyDatabaseEnforcementTests(SimpleTestCase):
    @patch.dict(os.environ, {"DEPLOYMENT_READ_ONLY": "true"}, clear=False)
    def test_new_postgres_connections_are_forced_read_only(self):
        connection = FakeConnection()

        enforce_read_only_connection(connection=connection)

        self.assertEqual(
            connection.cursor_instance.statements,
            ["SET default_transaction_read_only = on"],
        )

    @patch.dict(os.environ, {"DEPLOYMENT_READ_ONLY": "true"}, clear=False)
    def test_runtime_state_requires_default_and_current_transaction(self):
        connection = FakeConnection(["on", "on"])

        self.assertTrue(database_read_only_state(connection))
        self.assertEqual(
            connection.cursor_instance.statements,
            [
                "SHOW default_transaction_read_only",
                "SHOW transaction_read_only",
            ],
        )

    @patch.dict(os.environ, {"DEPLOYMENT_READ_ONLY": "false"}, clear=False)
    def test_active_mode_does_not_claim_read_only_enforcement(self):
        self.assertFalse(database_read_only_state(FakeConnection(["on", "on"])))
