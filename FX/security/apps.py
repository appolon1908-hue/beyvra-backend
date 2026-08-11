import logging

from django.apps import AppConfig
from django.core.exceptions import ObjectDoesNotExist
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


def create_periodic_task(**_kwargs):
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    try:
        # Create a 5min interval Anomaly Check on User Activities
        interval, _ = IntervalSchedule.objects.get_or_create(every=5, period=IntervalSchedule.MINUTES)

        PeriodicTask.objects.get_or_create(
            interval=interval,
            name="Security Check for User Anomalies",
            task="security.tasks.async_check_anomalies",
            enabled=True,
        )
    except ObjectDoesNotExist:
        logging.warning("Could not access the models: AnomalyCheckSchedule or UserActivity.")
