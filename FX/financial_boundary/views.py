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


def feature_disabled():
    return Response(
        {"code": "FEATURE_DISABLED", "title": "Feature unavailable", "detail": "This financial feature is not available."},
        status=503,
    )


class CanonicalFinancialView(APIView):
    permission_classes = (IsAuthenticated,)
    feature = "wallet"

    def _response(self):
        # No client/model/provider is instantiated while the gate is false.
        if not getattr(settings, FEATURES[self.feature], False) or not settings.REAL_MONEY_ENABLED:
            return feature_disabled()
        # Activation requires a separately reviewed implementation milestone.
        return feature_disabled()

    get = lambda self, request, **kwargs: self._response()
    post = lambda self, request, **kwargs: self._response()


class WalletView(CanonicalFinancialView):
    feature = "wallet"


class DepositView(CanonicalFinancialView):
    feature = "deposit"


class WithdrawalView(CanonicalFinancialView):
    feature = "withdrawal"


class TransferView(CanonicalFinancialView):
    feature = "transfer"
