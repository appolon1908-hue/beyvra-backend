import logging

from django.apps import AppConfig
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "security"

    def ready(self):
        # Ensure this code only runs once all apps are loaded
        from security.models import AnomalyCheckSchedule, UserActivity

        try:
            if is_model_migrated(AnomalyCheckSchedule) and is_model_migrated(UserActivity):
                # Trigger task creation on app startup
                create_periodic_task()
        except DatabaseError:
            logging.warning("Tables for AnomalyCheckSchedule or UserActivity are not yet available.")


def is_model_migrated(model):
    """
    Check if the model has been migrated by checking the table existence using Django's ORM.
    """
    try:
        # Attempt to access any object in the model's table. If the table does not exist,
        model.objects.exists()
        return True
    except DatabaseError:
        return False


def create_periodic_task():
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
