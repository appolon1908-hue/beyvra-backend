from django.urls import path

from .views import CalendarView, CorporateActionListView, InstrumentDetailView, InstrumentListView, MarketStatusView, ProviderMappingView, ReconciliationView
from .market_data_views import (
    CanonicalMarketCandlesView,
    CanonicalMarketCapabilitiesView,
    CanonicalMarketOrderBookView,
    CanonicalMarketSnapshotView,
    CanonicalMarketTradesView,
)

urlpatterns = [
    path("instruments", InstrumentListView.as_view(), name="canonical-instruments"),
    path("instruments/<uuid:instrument_id>", InstrumentDetailView.as_view(), name="canonical-instrument-detail"),
    path("markets/status", MarketStatusView.as_view(), name="canonical-markets-status"),
    path("market/snapshot", CanonicalMarketSnapshotView.as_view(), name="canonical-market-snapshot"),
    path("market/candles", CanonicalMarketCandlesView.as_view(), name="canonical-market-candles"),
    path("market/order-book", CanonicalMarketOrderBookView.as_view(), name="canonical-market-order-book"),
    path("market/trades", CanonicalMarketTradesView.as_view(), name="canonical-market-trades"),
    path("market/capabilities", CanonicalMarketCapabilitiesView.as_view(), name="canonical-market-capabilities"),
    path("market/instruments", InstrumentListView.as_view(), name="reference-instrument-list"),
    path("market/instruments/<uuid:instrument_id>", InstrumentDetailView.as_view(), name="reference-instrument-detail"),
    path("market/calendar", CalendarView.as_view(), name="reference-calendar"),
    path("market/corporate-actions", CorporateActionListView.as_view(), name="reference-corporate-actions"),
    path("market/status", MarketStatusView.as_view(), name="reference-market-status"),
    path("internal/reference-data/reconciliation", ReconciliationView.as_view(), name="reference-reconciliation"),
    path("internal/reference-data/provider-mappings/<uuid:instrument_id>", ProviderMappingView.as_view(), name="reference-provider-mappings"),
]
