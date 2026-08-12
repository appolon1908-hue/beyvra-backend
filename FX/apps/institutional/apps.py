from django.apps import AppConfig


class InstitutionalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.institutional"
    label = "institutional"

    def ready(self):
        from . import metrics  # noqa: F401
