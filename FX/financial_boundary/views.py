from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


FEATURES = {
    "wallet": "REAL_WALLET_READ_ENABLED",
    "deposit": "REAL_DEPOSITS_ENABLED",
    "withdrawal": "REAL_WITHDRAWALS_ENABLED",
    "transfer": "REAL_INTERNAL_TRANSFERS_ENABLED",
}


def feature_disabled(feature):
    feature_name = {
        "wallet": "real_wallet_read_enabled",
        "deposit": "real_wallet_deposits_enabled",
        "withdrawal": "real_wallet_withdrawals_enabled",
        "transfer": "real_wallet_transfers_enabled",
    }[feature]
    return Response(
        {"code": "FEATURE_DISABLED", "message": "This financial feature is not available.", "details": {}, "feature": feature_name, "error": {"code": "FEATURE_DISABLED", "message": "This financial feature is not available.", "details": {}}},
        status=503,
    )


class CanonicalFinancialView(APIView):
    permission_classes = (IsAuthenticated,)
    feature = "wallet"

    def _response(self):
        # No client/model/provider is instantiated while the gate is false.
        if not getattr(settings, FEATURES[self.feature], False) or not settings.REAL_MONEY_ENABLED:
            return feature_disabled(self.feature)
        # Activation requires a separately reviewed implementation milestone.
        return feature_disabled(self.feature)

    def get(self, request, **kwargs):
        return self._response()

    def post(self, request, **kwargs):
        return self._response()


class FinancialFeaturesView(APIView):
    permission_classes = ()

    def get(self, request):
        return Response({"features": {key: False for key in FEATURES}})


class WalletView(CanonicalFinancialView):
    feature = "wallet"


class DepositView(CanonicalFinancialView):
    feature = "deposit"


class WithdrawalView(CanonicalFinancialView):
    feature = "withdrawal"


class TransferView(CanonicalFinancialView):
    feature = "transfer"
