from django.urls import path

from platform_ops.health.api import (
    CapabilitiesView,
    ReleaseIdentityView,
    SystemStatusView,
)

urlpatterns = [
    path("status", SystemStatusView.as_view(), name="system-status"),
    path(
        "capabilities",
        CapabilitiesView.as_view(),
        name="system-capabilities",
    ),
    path("version", ReleaseIdentityView.as_view(), name="system-version"),
]
