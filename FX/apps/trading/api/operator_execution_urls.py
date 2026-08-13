from django.urls import path
from .execution_views import OperatorProviderCapabilityView, OperatorProviderControlView, OperatorProviderDetailView, OperatorProviderHealthView, OperatorProviderPaperEnableView, OperatorProviderResumeView, OperatorProvidersView, OperatorQualityView, OperatorReconciliationView, OperatorRouteDetailView, OperatorRoutesView, OperatorUnknownReconcileView, OperatorUnknownView, OperatorVenuesView

urlpatterns = [
    path("providers", OperatorProvidersView.as_view()),
    path("providers/<str:provider_code>", OperatorProviderDetailView.as_view()),
    path("providers/<str:provider_code>/capabilities", OperatorProviderCapabilityView.as_view()),
    path("providers/<str:provider_code>/health", OperatorProviderHealthView.as_view()),
    path("venues", OperatorVenuesView.as_view()),
    path("routes", OperatorRoutesView.as_view()),
    path("routes/<uuid:order_id>", OperatorRouteDetailView.as_view()),
    path("quality", OperatorQualityView.as_view()),
    path("unknown", OperatorUnknownView.as_view()),
    path("unknown/<uuid:outcome_id>/reconcile", OperatorUnknownReconcileView.as_view()),
    path("reconciliation", OperatorReconciliationView.as_view()),
    path("providers/<str:provider_id>/halt", OperatorProviderControlView.as_view()),
    path("providers/<str:provider_id>/resume", OperatorProviderResumeView.as_view()),
    path("providers/<str:provider_id>/paper-enable", OperatorProviderPaperEnableView.as_view()),
]
