from django.urls import path
from trade import views
from trade.demo_engine import DemoOrderView, DemoTradeListView
from .market_api import (
    FeedHealthView,
    InstrumentRegistryView,
    MarketCandlesView,
    MarketCapabilityUnsupportedView,
    MarketQuotesView,
    MarketStatusView,
    MarketTradesView,
)

app_name = "trade"

urlpatterns = [
    path("demo/orders", DemoOrderView.as_view(), name="demo_order"),
    path("demo/trades", DemoTradeListView.as_view(), name="demo_trades"),
    path("", views.TradeListCreateView.as_view(), name="trade_list_create"),
    path("<int:pk>/", views.TradeDetailView.as_view(), name="trade_detail"),
    path("<int:pk>/cancel/", views.TradeCancelView.as_view(), name="trade_cancel"),
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("market/history/", views.MarketHistoryView.as_view(), name="market_history"),
    path("market/instruments", InstrumentRegistryView.as_view(), name="market_instruments"),
    path("market/instruments/<str:symbol>", InstrumentRegistryView.as_view(), name="market_instrument_detail"),
    path("market/candles", MarketCandlesView.as_view(), name="market_candles"),
    path("market/quotes", MarketQuotesView.as_view(), name="market_quotes"),
    path("market/status/<str:symbol>", MarketStatusView.as_view(), name="market_status"),
    path("market/orderbook/<str:symbol>", MarketCapabilityUnsupportedView.as_view(), name="market_orderbook"),
    path("market/trades/<str:symbol>", MarketTradesView.as_view(), name="market_trades"),
    path("market/feed-health", FeedHealthView.as_view(), name="market_feed_health"),
]
