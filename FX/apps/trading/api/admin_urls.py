from django.urls import path

from .admin_views import InstrumentHaltView, InstrumentResumeView, PlatformHaltView, PlatformResumeView

urlpatterns = [
    path("trading/halt", PlatformHaltView.as_view()),
    path("trading/resume", PlatformResumeView.as_view()),
    path("instruments/<str:instrument>/halt", InstrumentHaltView.as_view()),
    path("instruments/<str:instrument>/resume", InstrumentResumeView.as_view()),
]
