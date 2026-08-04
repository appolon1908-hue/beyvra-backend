from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def disabled_response(request, feature):
    return Response(
        {
            "type": "https://errors.codestra.example/wallet/feature-disabled",
            "title": "Real wallet feature disabled",
            "status": 503,
            "detail": "Real-value wallet operations are disabled until staging approval.",
            "instance": request.path,
            "code": "FEATURE_DISABLED",
            "request_id": request.headers.get("X-Request-ID", ""),
            "errors": [],
            "feature": feature,
        },
        status=503,
    )


class RealWalletDisabledView(APIView):
    permission_classes = (IsAuthenticated,)
    feature = "real_wallet_read_enabled"

    def get(self, request, *args, **kwargs):
        return disabled_response(request, self.feature)

    def post(self, request, *args, **kwargs):
        return disabled_response(request, self.feature)

    def patch(self, request, *args, **kwargs):
        return disabled_response(request, self.feature)

    def delete(self, request, *args, **kwargs):
        return disabled_response(request, self.feature)


class RealWalletStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response({"enabled": False, "mode": "disabled", "demo_isolation": True})
