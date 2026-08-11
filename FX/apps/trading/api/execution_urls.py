from django.urls import path
from .execution_views import CapabilitiesView, CapabilityDetailView, ExecutionPreviewView, ProviderStatusView, QualityView, ReportView, ReportsView, RouteView, VenueDetailView, VenuesView

urlpatterns = [
    path("preview", ExecutionPreviewView.as_view()),
    path("capabilities", CapabilitiesView.as_view()),
    path("capabilities/<str:provider_code>", CapabilityDetailView.as_view()),
    path("venues", VenuesView.as_view()),
    path("venues/<str:venue_id>", VenueDetailView.as_view()),
    path("providers/status", ProviderStatusView.as_view()),
    path("routes/<uuid:order_id>", RouteView.as_view()),
    path("quality/<uuid:order_id>", QualityView.as_view()),
    path("reports", ReportsView.as_view()),
    path("reports/<uuid:report_id>", ReportView.as_view()),
]
