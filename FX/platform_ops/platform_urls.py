from django.urls import path
from platform_ops.platform_api import PlatformConfigView, PlatformCapabilitiesView

urlpatterns = [
    path("config", PlatformConfigView.as_view(), name="platform-config"),
    path("capabilities", PlatformCapabilitiesView.as_view(), name="platform-capabilities"),
]
