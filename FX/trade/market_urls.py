from django.urls import path

from .market_api import FeedHealthView, InstrumentRegistryView, MarketCandlesView, MarketQuotesView, MarketStatusView, MarketCapabilityUnsupportedView

urlpatterns = [
    path("market/instruments", InstrumentRegistryView.as_view()),
    path("market/instruments/<str:symbol>", InstrumentRegistryView.as_view()),
    path("market/candles", MarketCandlesView.as_view()),
    path("market/quotes", MarketQuotesView.as_view()),
    path("market/status/<str:symbol>", MarketStatusView.as_view()),
    path("market/orderbook/<str:symbol>", MarketCapabilityUnsupportedView.as_view()),
    path("market/trades/<str:symbol>", MarketCapabilityUnsupportedView.as_view()),
    path("market/feed-health", FeedHealthView.as_view()),
]
