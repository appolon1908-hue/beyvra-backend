from django.urls import path
from .execution_views import OperatorProviderControlView, OperatorProviderResumeView, OperatorProvidersView, OperatorQualityView, OperatorRoutesView

urlpatterns = [
    path("providers", OperatorProvidersView.as_view()),
    path("routes", OperatorRoutesView.as_view()),
    path("quality", OperatorQualityView.as_view()),
    path("providers/<str:provider_id>/halt", OperatorProviderControlView.as_view()),
    path("providers/<str:provider_id>/resume", OperatorProviderResumeView.as_view()),
]
