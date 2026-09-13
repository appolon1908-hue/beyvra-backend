from decimal import Decimal

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.trading.application.simulation import account_for, serialize_account
from apps.trading.application.accounts import serialize_trading_account
from integrations.permissions import organization_for_request

from trade.models import Asset
from .serializers import WorkspaceBootstrapSerializer


ALLOWED_DURATIONS = {5, 15, 30, 60}
PAYOUT_RATE = Decimal("0.80")
FIXED_TIME_MIN_AMOUNT = Decimal("1")
FIXED_TIME_MAX_AMOUNT = Decimal("10000")
FIXED_TIME_AMOUNT_STEP = Decimal("1")


class WorkspaceBootstrapView(APIView):
    """Hydrate the UI from the canonical simulation account read model."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: WorkspaceBootstrapSerializer})
    def get(self, request):
        organization = organization_for_request(request)
        account = account_for(request.user, str(organization.id))
        account_data = serialize_account(account)
        symbols = list(Asset.objects.values_list("symbol", flat=True)[:100]) or [
            "BTCUSDT"
        ]
        guest = bool(getattr(request.user, "is_guest_demo", False))
        account_channel_ref = f"sim-{request.user.pk}"
        return Response(
            {
                "state": "guest.ready" if guest else "user.ready",
                "tenant": {"id": str(organization.id)},
                "account": {
                    "id": str(account.id),
                    **serialize_trading_account(account.trading_account),
                },
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
                "features": {
                    "inZone": False,
                    "payments": False,
                    "realWallets": False,
                    "realTrading": False,
                },
                "instrument": {"symbol": symbols[0], "marketStatus": "OPEN"},
                "instruments": symbols,
                "tradingRules": {
                    "durations": sorted(ALLOWED_DURATIONS),
                    "minAmount": str(FIXED_TIME_MIN_AMOUNT),
                    "maxAmount": str(FIXED_TIME_MAX_AMOUNT),
                    "amountStep": str(FIXED_TIME_AMOUNT_STEP),
                    "payoutRate": str(PAYOUT_RATE),
                },
                "savedAssetTabs": symbols[:5],
                "chartPreferences": {"interval": "1m", "chartType": "candlesticks"},
            }
        )
