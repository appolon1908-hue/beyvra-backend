from django.conf import settings

from apps.foundation.observability import record_live_effect


def cancel_order(*_args, **_kwargs):
    if (
        not settings.REAL_TRADING_ENABLED
        or not settings.EXTERNAL_EXECUTION_ENABLED
    ):
        raise RuntimeError("FEATURE_DISABLED")
    record_live_effect("broker_order_cancel", "attempt")
    record_live_effect("broker_order_cancel", "failure")
    raise RuntimeError("PROVIDER_UNAVAILABLE")
