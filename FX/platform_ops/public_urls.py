from django.urls import path
from platform_ops.health.api import SystemStatusView,CapabilitiesView
urlpatterns=[path("status",SystemStatusView.as_view(),name="system-status"),path("capabilities",CapabilitiesView.as_view(),name="system-capabilities")]
