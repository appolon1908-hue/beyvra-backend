from django.apps import AppConfig


class FoundationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.foundation"
    label = "foundation"

    def ready(self):
        from . import checks  # noqa: F401
