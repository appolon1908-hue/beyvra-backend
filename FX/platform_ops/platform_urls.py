from django.urls import path

from platform_ops.platform_api import (
    PlatformCapabilitiesView,
    PlatformConfigView,
)

urlpatterns = [
    path("config", PlatformConfigView.as_view(), name="platform-config"),
    path(
        "capabilities",
        PlatformCapabilitiesView.as_view(),
        name="platform-capabilities",
    ),
]
