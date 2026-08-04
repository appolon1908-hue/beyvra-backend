from django.urls import path
from trade import views
from trade.demo_engine import DemoOrderView, DemoTradeListView

app_name = "trade"

urlpatterns = [
    path("demo/orders", DemoOrderView.as_view(), name="demo_order"),
    path("demo/trades", DemoTradeListView.as_view(), name="demo_trades"),
    path("", views.TradeListCreateView.as_view(), name="trade_list_create"),
    path("<int:pk>/", views.TradeDetailView.as_view(), name="trade_detail"),
    path("<int:pk>/cancel/", views.TradeCancelView.as_view(), name="trade_cancel"),
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("market/history/", views.MarketHistoryView.as_view(), name="market_history"),
]
