from django.urls import path
from .api import ComplianceProfileView, ComplianceRequirementsView, ComplianceWebhookView, KycSessionView
urlpatterns = [path("profile", ComplianceProfileView.as_view()), path("requirements", ComplianceRequirementsView.as_view()), path("kyc/sessions", KycSessionView.as_view()), path("webhooks/<str:provider_key>", ComplianceWebhookView.as_view())]
