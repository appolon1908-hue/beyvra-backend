from django.urls import path

from .admin_portal import AdminPortalEventsView, AdminPortalSummaryView, AdminPortalUsersView

urlpatterns = [
    path("summary", AdminPortalSummaryView.as_view(), name="admin_portal_summary"),
    path("users", AdminPortalUsersView.as_view(), name="admin_portal_users"),
    path("events", AdminPortalEventsView.as_view(), name="admin_portal_events"),
]
