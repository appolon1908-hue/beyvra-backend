from types import SimpleNamespace
from unittest.mock import patch

from django.db import connections
from django.test import SimpleTestCase

from security.apps import create_periodic_task


class PeriodicTaskMigrationOrderTests(SimpleTestCase):
    databases = {"default"}

    @patch(
        "django.db.backends.base.introspection."
        "BaseDatabaseIntrospection.table_names"
    )
    def test_missing_celery_beat_tables_are_skipped(self, table_names):
        table_names.return_value = []

        create_periodic_task(using="default")

        table_names.assert_called_once()

    def test_incomplete_celery_beat_schema_is_skipped(self):
        introspection = connections["default"].introspection
        with patch.object(
            introspection,
            "table_names",
            return_value=[
                "django_celery_beat_intervalschedule",
                "django_celery_beat_periodictask",
            ],
        ), patch.object(
            introspection,
            "get_table_description",
            return_value=[SimpleNamespace(name="id")],
        ) as describe:
            create_periodic_task(using="default")

        self.assertEqual(describe.call_count, 1)
