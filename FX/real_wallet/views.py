import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.models import OrganizationMembership
from .models import Asset, AssetNetwork, Deposit, FeatureFlag, Network, RealWallet, Withdrawal, WithdrawalAddress, WebhookSubscription, ReconciliationRun
from .serializers import RealWalletBalanceSerializer, RealWalletSerializer
from .services import is_feature_enabled, approve_withdrawal
from .reconciliation import run_balance_reconciliation
from .webhooks import WebhookSecurityError, create_secret_version, validate_webhook_destination

def disabled_response(request, feature):
    return Response(
        {
            # Compatibility aliases for the pre-v1 boundary tests and callers.
            # Canonical clients consume the nested Beyvra error object below.
            "code": "FEATURE_DISABLED",
            "message": "This feature is not enabled.",
            "details": [],
            "feature": feature,
            "error": {
                "code": "FEATURE_DISABLED",
                "message": "This feature is not enabled.",
                "details": [],
            },
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


def _owned_wallet(request, wallet_id):
    return RealWallet.objects.filter(
        id=wallet_id, owner=request.user,
        tenant__memberships__user=request.user,
        tenant__memberships__organization__is_active=True,
    ).first()


class WalletAddressesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, wallet_id):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        wallet = _owned_wallet(request, wallet_id)
        if wallet is None:
            return Response({"detail": "Not found."}, status=404)
        addresses = WithdrawalAddress.objects.filter(wallet=wallet).select_related("asset_network__asset", "asset_network__network")
        return Response({"results": [
            {"id": str(item.id), "address": item.address, "status": item.status,
             "risk_state": item.risk_state, "cooling_until": item.cooling_until,
             "asset": item.asset_network.asset.symbol, "network": item.asset_network.network.code}
            for item in addresses.order_by("created_at")
        ]})


class DepositListView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        # Deposit initiation is intentionally unavailable until the real-money
        # activation gate is independently approved and implemented.
        return disabled_response(request, "real_wallet_deposits_enabled")

    def get(self, request):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        deposits = Deposit.objects.filter(wallet__owner=request.user, wallet__tenant__memberships__user=request.user).select_related("asset_network__asset", "asset_network__network")
        return Response({"results": [
            {"id": str(item.id), "wallet_id": str(item.wallet_id), "state": item.state,
             "amount_atomic": str(item.amount_atomic), "confirmations": item.confirmations,
             "transaction_hash": item.transaction_hash, "asset": item.asset_network.asset.symbol,
             "network": item.asset_network.network.code}
            for item in deposits.order_by("-created_at")
        ]})


class WithdrawalListView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        # Withdrawal initiation must fail closed rather than exposing a generic
        # method error while the real-money boundary is disabled.
        return disabled_response(request, "real_wallet_withdrawals_enabled")

    def get(self, request):
        if not is_feature_enabled("real_wallet_read_enabled"):
            return disabled_response(request, "real_wallet_read_enabled")
        withdrawals = Withdrawal.objects.filter(wallet__owner=request.user, wallet__tenant__memberships__user=request.user).select_related("asset_network__asset", "asset_network__network")
        return Response({"results": [
            {"id": str(item.id), "wallet_id": str(item.wallet_id), "state": item.state,
             "amount_atomic": str(item.amount_atomic), "fee_atomic": str(item.fee_atomic),
             "destination": item.destination, "blockchain_transaction": item.blockchain_transaction,
             "asset": item.asset_network.asset.symbol, "network": item.asset_network.network.code}
            for item in withdrawals.order_by("-created_at")
        ]})


def _request_tenant(request):
    membership = OrganizationMembership.objects.select_related("organization").filter(
        user=request.user, organization__is_active=True
    ).order_by("organization_id").first()
    return membership.organization if membership else None


def _admin_tenant(request):
    membership = OrganizationMembership.objects.select_related("organization").filter(
        user=request.user, organization__is_active=True, role__in=("owner", "admin")
    ).order_by("organization_id").first()
    return membership.organization if membership else None


class AdminWithdrawalApprovalView(APIView):
    """Organization-admin approval boundary; real withdrawals remain feature-gated."""
    permission_classes = (IsAuthenticated,)

    def post(self, request, withdrawal_id):
        tenant = _admin_tenant(request)
        if tenant is None:
            return Response({"code": "AUTHORIZATION_DENIED", "detail": "Organization administrator required."}, status=403)
        withdrawal = Withdrawal.objects.filter(id=withdrawal_id, wallet__tenant=tenant).first()
        if withdrawal is None:
            return Response({"code": "RESOURCE_NOT_FOUND", "detail": "Withdrawal not found."}, status=404)
        try:
            result = approve_withdrawal(withdrawal_id=withdrawal.id, approver=request.user, decision="APPROVED")
        except ValueError as exc:
            return Response({"code": "VALIDATION_FAILED", "detail": str(exc)}, status=409)
        return Response({"id": str(result.id), "status": result.state})


class AdminWithdrawalRejectView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, withdrawal_id):
        tenant = _admin_tenant(request)
        if tenant is None:
            return Response({"code": "AUTHORIZATION_DENIED", "detail": "Organization administrator required."}, status=403)
        withdrawal = Withdrawal.objects.filter(id=withdrawal_id, wallet__tenant=tenant).first()
        if withdrawal is None:
            return Response({"code": "RESOURCE_NOT_FOUND", "detail": "Withdrawal not found."}, status=404)
        try:
            result = approve_withdrawal(withdrawal_id=withdrawal.id, approver=request.user, decision="REJECTED", reason=str(request.data.get("reason", "")))
        except ValueError as exc:
            return Response({"code": "VALIDATION_FAILED", "detail": str(exc)}, status=409)
        return Response({"id": str(result.id), "status": result.state})


class AdminReconciliationView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        tenant = _admin_tenant(request)
        if tenant is None:
            return Response({"code": "AUTHORIZATION_DENIED", "detail": "Organization administrator required."}, status=403)
        runs = ReconciliationRun.objects.filter(tenant=tenant).order_by("-created_at")[:50]
        return Response({"results": [{"id": str(run.id), "scope": run.scope, "status": run.status, "summary": run.summary} for run in runs]})

    def post(self, request):
        tenant = _admin_tenant(request)
        if tenant is None:
            return Response({"code": "AUTHORIZATION_DENIED", "detail": "Organization administrator required."}, status=403)
        snapshot = request.data.get("external_balances", {})
        if not isinstance(snapshot, dict):
            return Response({"code": "VALIDATION_FAILED", "detail": "external_balances must be an object."}, status=400)
        run = run_balance_reconciliation(tenant=tenant, external_balances=snapshot)
        return Response({"id": str(run.id), "status": run.status, "summary": run.summary}, status=201)


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
