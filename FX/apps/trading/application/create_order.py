from django.conf import settings


def create_order(*_args, **_kwargs):
    if not settings.REAL_TRADING_ENABLED or not settings.EXTERNAL_EXECUTION_ENABLED:
        raise RuntimeError("FEATURE_DISABLED")
    raise RuntimeError("PROVIDER_UNAVAILABLE")
