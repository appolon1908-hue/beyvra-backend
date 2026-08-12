from decimal import Decimal

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.application.simulation import account_for, serialize_account
from integrations.permissions import organization_for_request

from .models import Asset


ALLOWED_DURATIONS = {5, 15, 30, 60}
PAYOUT_RATE = Decimal("0.80")
DEMO_MIN_AMOUNT = Decimal("1")
DEMO_MAX_AMOUNT = Decimal("10000")
DEMO_AMOUNT_STEP = Decimal("1")


class DemoConfigView(APIView):
    """Compatibility read model for practice-terminal presentation limits."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        symbols = list(Asset.objects.values_list("symbol", flat=True)[:100])
        return Response({
            "durations": sorted(ALLOWED_DURATIONS),
            "minAmount": int(DEMO_MIN_AMOUNT),
            "maxAmount": int(DEMO_MAX_AMOUNT),
            "amountStep": int(DEMO_AMOUNT_STEP),
            "payoutRate": str(PAYOUT_RATE),
            "assets": symbols or ["BTCUSDT"],
        })


class WorkspaceBootstrapView(APIView):
    """Hydrate the UI from the canonical simulation account read model."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organization = organization_for_request(request)
        account = account_for(request.user)
        account_data = serialize_account(account)
        symbols = list(Asset.objects.values_list("symbol", flat=True)[:100]) or ["BTCUSDT"]
        guest = bool(getattr(request.user, "is_guest_demo", False))
        account_channel_ref = f"sim-{request.user.pk}"
        return Response({
            "state": "guest.ready" if guest else "user.ready",
            "tenant": {"id": str(organization.id)},
            "account": {"id": str(account.id), "kind": "DEMO", "demoOnly": True},
            "realtime": {
                "demo_order_channel": f"simulation.order.{account_channel_ref}",
                "demo_execution_channel": f"simulation.execution.{account_channel_ref}",
            },
            "wallet": {
                "currency": "Virtual USD",
                "available": account_data["available"],
                "reserved": account_data["reserved"],
                "total": account_data["total"],
            },
            "notifications": {"unreadCount": 0},
            "features": {"inZone": False, "payments": False, "realWallets": False, "realTrading": False},
            "instrument": {"symbol": symbols[0], "marketStatus": "OPEN"},
            "instruments": symbols,
            "tradingRules": {
                "durations": sorted(ALLOWED_DURATIONS),
                "minAmount": str(DEMO_MIN_AMOUNT),
                "maxAmount": str(DEMO_MAX_AMOUNT),
                "amountStep": str(DEMO_AMOUNT_STEP),
                "payoutRate": str(PAYOUT_RATE),
            },
            "savedAssetTabs": symbols[:5],
            "chartPreferences": {"interval": "1m", "chartType": "candlesticks"},
        })
