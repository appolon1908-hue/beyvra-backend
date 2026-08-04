from django.urls import path

from .views import RealWalletDisabledView, RealWalletStatusView

app_name = "real_wallet"
disabled = RealWalletDisabledView.as_view()

urlpatterns = [
    path("status/", RealWalletStatusView.as_view(), name="status"),
    path("wallets/", disabled, name="wallets"),
    path("wallets/<uuid:wallet_id>/", disabled, name="wallet-detail"),
    path("wallets/<uuid:wallet_id>/balances/", disabled, name="wallet-balances"),
    path("wallets/<uuid:wallet_id>/addresses/", disabled, name="wallet-addresses"),
    path("deposits/", disabled, name="deposits"),
    path("deposits/<uuid:deposit_id>/", disabled, name="deposit-detail"),
    path("withdrawals/", disabled, name="withdrawals"),
    path("withdrawals/preview/", disabled, name="withdrawal-preview"),
    path("withdrawals/<uuid:withdrawal_id>/", disabled, name="withdrawal-detail"),
    path("transfers/", disabled, name="transfers"),
    path("transfers/<uuid:transfer_id>/", disabled, name="transfer-detail"),
    path("webhook-subscriptions/", disabled, name="webhook-subscriptions"),
]
