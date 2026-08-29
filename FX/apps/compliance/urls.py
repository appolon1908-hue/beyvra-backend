from django.urls import path
from .api import ComplianceProfileView, ComplianceRequirementsView, ComplianceWebhookView, KycSessionView
from .workflow_views import (
    ComplianceAcknowledgementsView,
    ComplianceDocumentsView,
    ComplianceRestrictionsView,
    ComplianceStatusView,
    UnderwritingWorkflowView,
)

urlpatterns = [
    path("status", ComplianceStatusView.as_view(), name="compliance-status"),
    path("underwriting/workflow", UnderwritingWorkflowView.as_view(), name="compliance-underwriting-workflow"),
    path("restrictions", ComplianceRestrictionsView.as_view(), name="compliance-restrictions"),
    path("documents", ComplianceDocumentsView.as_view(), name="compliance-documents"),
    path("acknowledgements", ComplianceAcknowledgementsView.as_view(), name="compliance-acknowledgements"),
    path("profile", ComplianceProfileView.as_view()),
    path("profile/", ComplianceProfileView.as_view()),
    path("requirements", ComplianceRequirementsView.as_view()),
    path("requirements/", ComplianceRequirementsView.as_view()),
    path("kyc/sessions", KycSessionView.as_view()),
    path("webhooks/<str:provider_key>", ComplianceWebhookView.as_view()),
]
