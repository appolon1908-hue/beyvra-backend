from django.urls import path
from .views import DepositView, FinancialFeaturesView, TransferView, WalletView, WithdrawalView
from .canonical_webhook_views import CanonicalProviderWebhookView


urlpatterns = [
    path("webhooks/executions/<str:provider>", CanonicalProviderWebhookView.as_view(), name="webhook-executions"),
    path("webhooks/market-data/<str:provider>", CanonicalProviderWebhookView.as_view(), name="webhook-market-data"),
    path("webhooks/custody/<str:provider>", CanonicalProviderWebhookView.as_view(), name="webhook-custody"),
    path("features/", FinancialFeaturesView.as_view(), name="canonical-financial-features"),
    path("wallets/", WalletView.as_view(), name="canonical-wallet-list"),
    path("wallets/<str:asset>", WalletView.as_view(), name="canonical-wallet-detail"),
    path("wallets/<str:asset>/", WalletView.as_view(), name="canonical-wallet-detail-slash"),
    path("deposits/", DepositView.as_view(), name="canonical-deposit-list-create"),
    path("deposits/<uuid:operation_id>", DepositView.as_view(), name="canonical-deposit-detail"),
    path("deposits/<uuid:operation_id>/", DepositView.as_view(), name="canonical-deposit-detail-slash"),
    path("withdrawals/", WithdrawalView.as_view(), name="canonical-withdrawal-list-create"),
    path("withdrawals/preview/", WithdrawalView.as_view(), name="canonical-withdrawal-preview"),
    path("withdrawals/<uuid:operation_id>", WithdrawalView.as_view(), name="canonical-withdrawal-detail"),
    path("withdrawals/<uuid:operation_id>/", WithdrawalView.as_view(), name="canonical-withdrawal-detail-slash"),
    path("withdrawals/<uuid:operation_id>/cancel", WithdrawalView.as_view(), name="canonical-withdrawal-cancel"),
    path("withdrawals/<uuid:operation_id>/cancel/", WithdrawalView.as_view(), name="canonical-withdrawal-cancel-slash"),
    path("transfers/", TransferView.as_view(), name="canonical-transfer-list-create"),
    path("transfers/preview/", TransferView.as_view(), name="canonical-transfer-preview"),
    path("transfers/<uuid:operation_id>", TransferView.as_view(), name="canonical-transfer-detail"),
    path("transfers/<uuid:operation_id>/", TransferView.as_view(), name="canonical-transfer-detail-slash"),
]
