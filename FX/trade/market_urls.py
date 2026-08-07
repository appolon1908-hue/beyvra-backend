from django.urls import path

from .market_api import (
    FeedHealthView, InstrumentRegistryView, InstrumentTradingRulesV1View,
    InstrumentV1View, MarketCandlesV1View, MarketCandlesView,
    MarketQuotesView, MarketSnapshotV1View, MarketStatusV1View,
    MarketStatusView, MarketCapabilityUnsupportedView,
)

urlpatterns = [
    path("market-data/snapshot", MarketSnapshotV1View.as_view()),
    path("market-data/candles", MarketCandlesV1View.as_view()),
    path("market-data/status", MarketStatusV1View.as_view()),
    path("instruments/<str:instrument_id>/trading-rules", InstrumentTradingRulesV1View.as_view()),
    path("instruments/<str:instrument_id>", InstrumentV1View.as_view()),
    path("market/instruments", InstrumentRegistryView.as_view()),
    path("market/instruments/<str:symbol>", InstrumentRegistryView.as_view()),
    path("market/candles", MarketCandlesView.as_view()),
    path("market/quotes", MarketQuotesView.as_view()),
    path("market/status/<str:symbol>", MarketStatusView.as_view()),
    path("market/orderbook/<str:symbol>", MarketCapabilityUnsupportedView.as_view()),
    path("market/trades/<str:symbol>", MarketCapabilityUnsupportedView.as_view()),
    path("market/feed-health", FeedHealthView.as_view()),
]
