import logging

from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "security"

    def ready(self):
        post_migrate.connect(
            create_periodic_task,
            sender=self,
            dispatch_uid="security.create_periodic_task",
        )


def create_periodic_task(using="default", **_kwargs):
    """Create the anomaly schedule only after Celery Beat is fully migrated."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    connection = connections[using]
    required_tables = {
        IntervalSchedule._meta.db_table,
        PeriodicTask._meta.db_table,
    }
    existing_tables = set(connection.introspection.table_names())
    if not required_tables.issubset(existing_tables):
        logger.info(
            "Skipping security periodic task until django-celery-beat "
            "migrations are applied."
        )
        return

    # post_migrate fires after every application migration. The tables can
    # exist while later django-celery-beat columns are still absent, so verify
    # the concrete schema before allowing the ORM to query either model.
    with connection.cursor() as cursor:
        for model in (IntervalSchedule, PeriodicTask):
            actual_columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor,
                    model._meta.db_table,
                )
            }
            required_columns = {
                field.column
                for field in model._meta.concrete_fields
                if field.column
            }
            if not required_columns.issubset(actual_columns):
                logger.info(
                    "Skipping security periodic task until "
                    "django-celery-beat schema is current."
                )
                return

    interval, _ = IntervalSchedule.objects.using(using).get_or_create(
        every=5,
        period=IntervalSchedule.MINUTES,
    )
    PeriodicTask.objects.using(using).get_or_create(
        interval=interval,
        name="Security Check for User Anomalies",
        task="security.tasks.async_check_anomalies",
        enabled=True,
    )
