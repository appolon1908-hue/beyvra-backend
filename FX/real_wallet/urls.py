from django.urls import path

from .views import (
    RealWalletBalanceListView,
    RealWalletAssetNetworksView,
    RealWalletAssetsView,
    RealWalletDetailView,
    RealWalletDisabledView,
    RealWalletListView,
    RealWalletFeaturesView,
    RealWalletNetworksView,
    DepositListView,
    WalletAddressesView,
    WithdrawalListView,
    RealWalletStatusView,
    WebhookSubscriptionListCreateView,
    WebhookSubscriptionRotateSecretView,
    AdminWithdrawalApprovalView,
    AdminWithdrawalRejectView,
    AdminReconciliationView,
)

app_name = "real_wallet"
disabled = RealWalletDisabledView.as_view()

urlpatterns = [
    path("status/", RealWalletStatusView.as_view(), name="status"),
    path("features/", RealWalletFeaturesView.as_view(), name="features"),
    path("assets/", RealWalletAssetsView.as_view(), name="assets"),
    path("networks/", RealWalletNetworksView.as_view(), name="networks"),
    path("asset-networks/", RealWalletAssetNetworksView.as_view(), name="asset-networks"),
    path("wallets/", RealWalletListView.as_view(), name="wallets"),
    path("wallets/<uuid:wallet_id>/", RealWalletDetailView.as_view(), name="wallet-detail"),
    path("wallets/<uuid:wallet_id>/balances/", RealWalletBalanceListView.as_view(), name="wallet-balances"),
    path("wallets/<uuid:wallet_id>/addresses/", WalletAddressesView.as_view(), name="wallet-addresses"),
    path("deposits/", DepositListView.as_view(), name="deposits"),
    path("deposits/<uuid:deposit_id>/", disabled, name="deposit-detail"),
    path("withdrawals/", WithdrawalListView.as_view(), name="withdrawals"),
    path("withdrawals/preview/", disabled, name="withdrawal-preview"),
    path("withdrawals/<uuid:withdrawal_id>/", disabled, name="withdrawal-detail"),
    path("transfers/", disabled, name="transfers"),
    path("transfers/<uuid:transfer_id>/", disabled, name="transfer-detail"),
    path("webhook-subscriptions/", WebhookSubscriptionListCreateView.as_view(), name="webhook-subscriptions"),
    path("webhook-subscriptions/<uuid:subscription_id>/rotate-secret/", WebhookSubscriptionRotateSecretView.as_view(), name="webhook-subscription-rotate-secret"),
    path("admin/withdrawals/<uuid:withdrawal_id>/approve/", AdminWithdrawalApprovalView.as_view(), name="admin-withdrawal-approve"),
    path("admin/withdrawals/<uuid:withdrawal_id>/reject/", AdminWithdrawalRejectView.as_view(), name="admin-withdrawal-reject"),
    path("admin/reconciliations/", AdminReconciliationView.as_view(), name="admin-reconciliations"),
]
