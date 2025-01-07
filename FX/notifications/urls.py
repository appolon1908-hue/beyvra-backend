from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.NotificationListing.as_view(), name="notification_list"),
    path("toggle_notification/", views.UpdateNotifications.as_view(), name="toggle_notification"),
    path("alerts/", views.UserAlertsListing.as_view(), name="user_alerts"),
    path("alerts/<uuid:alert_id>/", views.UserAlertDetail.as_view(), name="user_alert_detail"),
]
