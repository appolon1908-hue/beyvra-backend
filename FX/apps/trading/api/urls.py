from django.urls import path

from .account_projections_views import (
    AccountBalancesProjectionView,
    AccountBuyingPowerProjectionView,
    AccountDetailProjectionView,
    AccountStatementsProjectionView,
    AccountTaxLotsProjectionView,
    AccountTransactionsProjectionView,
)
from .views import (
    AccountsView,
    EmptyDetailView,
    ExecutionsView,
    FeesView,
    OrderCancelView,
    OrderCollectionView,
    OrderDetailView,
    OrderEventsView,
    OrderPreviewView,
    OrderReplaceView,
    PortfolioView,
    PositionsView,
    TradeDetailView,
    TradesView,
)

urlpatterns = [
    path("orders/preview", OrderPreviewView.as_view()),
    path("orders", OrderCollectionView.as_view()),
    path("orders/<uuid:order_id>", OrderDetailView.as_view()),
    path("orders/<uuid:order_id>/cancel", OrderCancelView.as_view()),
    path("orders/<uuid:order_id>/replace", OrderReplaceView.as_view()),
    path("orders/<uuid:order_id>/events", OrderEventsView.as_view()),
    path("executions", ExecutionsView.as_view()),
    path("trades", TradesView.as_view()),
    path("trades/<uuid:trade_id>", TradeDetailView.as_view()),
    path("positions", PositionsView.as_view()),
    path("positions/<uuid:position_id>", EmptyDetailView.as_view()),
    path("accounts", AccountsView.as_view()),
    path("accounts/<uuid:account_id>", AccountDetailProjectionView.as_view()),
    path("accounts/<uuid:account_id>/balances", AccountBalancesProjectionView.as_view()),
    path("accounts/<uuid:account_id>/buying-power", AccountBuyingPowerProjectionView.as_view()),
    path("accounts/<uuid:account_id>/transactions", AccountTransactionsProjectionView.as_view()),
    path("accounts/<uuid:account_id>/statements", AccountStatementsProjectionView.as_view()),
    path("accounts/<uuid:account_id>/tax-lots", AccountTaxLotsProjectionView.as_view()),
    path("portfolio", PortfolioView.as_view()),
    path("fees", FeesView.as_view()),
]
