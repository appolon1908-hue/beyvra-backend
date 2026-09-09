from django.apps import AppConfig


class FoundationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.foundation"
    label = "foundation"

    def ready(self):
        from . import checks  # noqa: F401
        from .observability import (
            initialize_live_effect_metrics,
            set_safety_flags,
        )
        from .read_only import install_read_only_enforcement
        from django.conf import settings

        initialize_live_effect_metrics()
        set_safety_flags(settings)
        install_read_only_enforcement()
