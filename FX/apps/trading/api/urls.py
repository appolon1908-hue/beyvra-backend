from django.urls import path

from .views import AccountsView, EmptyDetailView, FeesView, OrderCancelView, OrderCollectionView, OrderDetailView, OrderPreviewView, OrderReplaceView, PortfolioView, PositionsView, TradeDetailView, TradesView

urlpatterns = [
    path("orders/preview", OrderPreviewView.as_view()),
    path("orders", OrderCollectionView.as_view()),
    path("orders/<uuid:order_id>", OrderDetailView.as_view()),
    path("orders/<uuid:order_id>/cancel", OrderCancelView.as_view()),
    path("orders/<uuid:order_id>/replace", OrderReplaceView.as_view()),
    path("trades", TradesView.as_view()),
    path("trades/<uuid:trade_id>", TradeDetailView.as_view()),
    path("positions", PositionsView.as_view()),
    path("positions/<uuid:position_id>", EmptyDetailView.as_view()),
    path("accounts", AccountsView.as_view()),
    path("portfolio", PortfolioView.as_view()),
    path("accounts/<uuid:account_id>", EmptyDetailView.as_view()),
    path("fees", FeesView.as_view()),
]
