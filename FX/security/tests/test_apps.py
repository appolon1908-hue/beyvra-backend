from unittest.mock import patch

from django.test import SimpleTestCase

from security.apps import create_periodic_task


class PeriodicTaskMigrationOrderTests(SimpleTestCase):
    databases = {"default"}

    @patch("django.db.backends.base.introspection.BaseDatabaseIntrospection.table_names")
    def test_missing_celery_beat_tables_are_skipped(self, table_names):
        table_names.return_value = []

        create_periodic_task(using="default")

        table_names.assert_called_once()
