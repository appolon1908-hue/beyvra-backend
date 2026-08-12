from django.apps import AppConfig


class PlatformOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_ops"

    def ready(self):
        from .observability import metrics  # noqa: F401
