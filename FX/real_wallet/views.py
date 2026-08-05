import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.models import OrganizationMembership
from .models import Asset, AssetNetwork, FeatureFlag, Network, RealWallet, WebhookSubscription
from .serializers import RealWalletBalanceSerializer, RealWalletSerializer
from .services import is_feature_enabled
from .webhooks import WebhookSecurityError, create_secret_version, validate_webhook_destination

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


class RealWalletFeaturesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        flags = FeatureFlag.objects.order_by("key")
        return Response({"features": {flag.key: flag.enabled for flag in flags}})


class RealWalletAssetsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({"results": [
            {"id": str(asset.id), "symbol": asset.symbol, "name": asset.name, "decimals": asset.decimals}
            for asset in Asset.objects.filter(enabled=True).order_by("symbol")
        ]})


class RealWalletNetworksView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({"results": [
            {"id": str(network.id), "code": network.code, "name": network.name}
            for network in Network.objects.filter(enabled=True).order_by("code")
        ]})


class RealWalletAssetNetworksView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        pairs = AssetNetwork.objects.filter(enabled=True, asset__enabled=True, network__enabled=True).select_related("asset", "network")
        return Response({"results": [
            {"id": str(pair.id), "asset_id": str(pair.asset_id), "network_id": str(pair.network_id),
             "symbol": pair.asset.symbol, "network": pair.network.code,
             "confirmations_required": pair.confirmations_required}
            for pair in pairs.order_by("asset__symbol", "network__code")
        ]})


class RealWalletListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        wallets = RealWallet.objects.filter(
            owner=request.user,
            tenant__memberships__user=request.user,
            tenant__memberships__organization__is_active=True,
        ).distinct().order_by("created_at")
        return Response({"results": RealWalletSerializer(wallets, many=True).data})


class RealWalletDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, wallet_id):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        wallet = RealWallet.objects.filter(
            id=wallet_id,
            owner=request.user,
            tenant__memberships__user=request.user,
            tenant__memberships__organization__is_active=True,
        ).first()
        if wallet is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(RealWalletSerializer(wallet).data)


class RealWalletBalanceListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, wallet_id):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        wallet = RealWallet.objects.filter(
            id=wallet_id,
            owner=request.user,
            tenant__memberships__user=request.user,
            tenant__memberships__organization__is_active=True,
        ).first()
        if wallet is None:
            return Response({"detail": "Not found."}, status=404)
        balances = wallet.balances.select_related("asset_network__asset", "asset_network__network").order_by("created_at")
        return Response({"results": RealWalletBalanceSerializer(balances, many=True).data})


def _request_tenant(request):
    membership = OrganizationMembership.objects.select_related("organization").filter(
        user=request.user, organization__is_active=True
    ).order_by("organization_id").first()
    return membership.organization if membership else None


class WebhookSubscriptionListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        tenant = _request_tenant(request)
        if tenant is None:
            return Response({"results": []})
        subscriptions = WebhookSubscription.objects.filter(tenant=tenant).order_by("created_at")
        return Response({
            "results": [
                {"id": str(item.id), "endpoint": item.endpoint, "status": item.status, "description": item.description}
                for item in subscriptions
            ]
        })

    @transaction.atomic
    def post(self, request):
        tenant = _request_tenant(request)
        if tenant is None:
            return Response({"code": "AUTHORIZATION_DENIED", "detail": "Organization membership required."}, status=403)
        endpoint = request.data.get("endpoint")
        if not isinstance(endpoint, str):
            return Response({"code": "VALIDATION_FAILED", "detail": "endpoint is required."}, status=400)
        try:
            validate_webhook_destination(endpoint)
        except WebhookSecurityError as exc:
            return Response({"code": "VALIDATION_FAILED", "detail": str(exc)}, status=400)
        secret = "whsec_" + secrets.token_urlsafe(32)
        subscription = WebhookSubscription.objects.create(
            tenant=tenant, endpoint=endpoint, description=str(request.data.get("description", ""))[:160], status="DISABLED"
        )
        key_id = "key_" + secrets.token_urlsafe(10)
        create_secret_version(subscription=subscription, secret=secret, key_id=key_id)
        return Response(
            {"id": str(subscription.id), "endpoint": endpoint, "status": subscription.status,
             "secret": secret, "secret_key_id": key_id, "secret_displayed_once": True},
            status=201,
        )


class WebhookSubscriptionRotateSecretView(APIView):
    permission_classes = (IsAuthenticated,)

    @transaction.atomic
    def post(self, request, subscription_id):
        tenant = _request_tenant(request)
        subscription = WebhookSubscription.objects.select_for_update().filter(
            id=subscription_id, tenant=tenant
        ).first()
        if subscription is None:
            return Response({"detail": "Not found."}, status=404)
        secret = "whsec_" + secrets.token_urlsafe(32)
        now = timezone.now()
        subscription.secret_versions.filter(revoked_at__isnull=True, expires_at__isnull=True).update(
            expires_at=now + timedelta(hours=1)
        )
        key_id = "key_" + secrets.token_urlsafe(10)
        create_secret_version(subscription=subscription, secret=secret, key_id=key_id)
        return Response({"secret": secret, "secret_key_id": key_id, "secret_displayed_once": True})
