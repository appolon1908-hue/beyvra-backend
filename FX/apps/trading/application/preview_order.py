from django.conf import settings

from apps.trading.risk import RiskEngine


def preview_order(payload):
    if not settings.REAL_TRADING_ENABLED:
        raise RuntimeError("FEATURE_DISABLED")
    return RiskEngine().evaluate_order(payload)
