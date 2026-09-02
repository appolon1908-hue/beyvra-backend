import logging

from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import post_migrate


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
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    connection = connections[using]
    required_tables = {
        IntervalSchedule._meta.db_table,
        PeriodicTask._meta.db_table,
    }
    existing_tables = set(connection.introspection.table_names())
    if not required_tables.issubset(existing_tables):
        logging.info(
            "Skipping security periodic task until django-celery-beat migrations are applied."
        )
        return

    # Create a 5min interval Anomaly Check on User Activities.
    interval, _ = IntervalSchedule.objects.using(using).get_or_create(
        every=5, period=IntervalSchedule.MINUTES
    )
    PeriodicTask.objects.using(using).get_or_create(
        interval=interval,
        name="Security Check for User Anomalies",
        task="security.tasks.async_check_anomalies",
        enabled=True,
    )
