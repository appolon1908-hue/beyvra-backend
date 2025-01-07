from django.apps import AppConfig


class TradeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trade"

    def ready(self) -> None:
        from . import signals  # noqa
