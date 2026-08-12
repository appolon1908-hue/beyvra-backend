from django.urls import path
from .views import DepositView, TransferView, WalletView, WithdrawalView


urlpatterns = [
    path("wallets/", WalletView.as_view(), name="canonical-wallet-list"),
    path("wallets/<str:asset>", WalletView.as_view(), name="canonical-wallet-detail"),
    path("deposits/", DepositView.as_view(), name="canonical-deposit-list-create"),
    path("deposits/<uuid:operation_id>", DepositView.as_view(), name="canonical-deposit-detail"),
    path("withdrawals/", WithdrawalView.as_view(), name="canonical-withdrawal-list-create"),
    path("withdrawals/<uuid:operation_id>", WithdrawalView.as_view(), name="canonical-withdrawal-detail"),
    path("withdrawals/<uuid:operation_id>/cancel", WithdrawalView.as_view(), name="canonical-withdrawal-cancel"),
    path("transfers/", TransferView.as_view(), name="canonical-transfer-list-create"),
    path("transfers/<uuid:operation_id>", TransferView.as_view(), name="canonical-transfer-detail"),
]
