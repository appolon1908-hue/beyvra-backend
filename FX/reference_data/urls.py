from django.urls import path

from .views import CalendarView, CorporateActionListView, InstrumentDetailView, InstrumentListView, MarketStatusView, ReconciliationView

urlpatterns = [
    path("market/instruments", InstrumentListView.as_view(), name="reference-instrument-list"),
    path("market/instruments/<uuid:instrument_id>", InstrumentDetailView.as_view(), name="reference-instrument-detail"),
    path("market/calendar", CalendarView.as_view(), name="reference-calendar"),
    path("market/corporate-actions", CorporateActionListView.as_view(), name="reference-corporate-actions"),
    path("market/status", MarketStatusView.as_view(), name="reference-market-status"),
    path("internal/reference-data/reconciliation", ReconciliationView.as_view(), name="reference-reconciliation"),
]
