from django.urls import include, path
from rest_framework import routers
from wallet import views
from bank_account_app.views import WithdrawalRequestView


router = routers.DefaultRouter()
router.register(r"transactions", views.TransactionViewSet)

app_name = "wallet"

urlpatterns = [
    path("", include(router.urls)),
    path("wallets/<int:wallet_id>/deposite/", views.DepositToWalletView.as_view()),
    path("wallets/<int:wallet_id>/withdraw/", views.WithdrawFromWalletView.as_view()),
    path("wallets/<int:wallet_id>/transfer/", views.TransferFromWalletView.as_view()),
    path("<int:pk>/archive/", views.WalletArchiveView.as_view(), name="archive_wallet"),
    path("currencies/", views.CurrencyList.as_view(), name="currency_list"),
    path("currency/<str:country>", views.get_currency),
    path("wallets/", views.WalletListCreateView.as_view(), name="wallet_list_create"),
    path("wallets/<int:pk>/", views.WalletDetailView.as_view(), name="wallet_detail"),
    path(
        "wallets/<int:pk>/refill/",
        views.WalletRefillView.as_view(),
        name="wallet_refill",
    ),

    path("withdrawal-request/", WithdrawalRequestView.as_view(), name="withdrawal-request"),
    path('manual-balance-updates/', views.ManualBalanceUpdateListCreateView.as_view()),
    path('manual-balance-updates/<int:pk>/', views.ManualBalanceUpdateDetailView.as_view()),
    path("wallet/withdraw/", views.WithdrawFundsView.as_view(), name="withdraw-funds"),
    path("wallet/withdraw-limited/", views.WithdrawWalletFundsView.as_view(), name="withdraw-funds-limited"),
]
