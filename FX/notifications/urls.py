from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("webhooks", views.WebhookSubscriptionViewSet, basename="notification-webhook")

urlpatterns = [
    path("", include(router.urls)),
    path("notifications/", views.NotificationListing.as_view(), name="notification_list"),
    path("toggle_notification/", views.UpdateNotifications.as_view(), name="toggle_notification"),
    path("alerts/", views.UserAlertsListing.as_view(), name="user_alerts"),
    path("alerts/<uuid:alert_id>/", views.UserAlertDetail.as_view(), name="user_alert_detail"),
    path("inbox/", views.NotificationInbox.as_view(), name="notification_inbox"),
    path("inbox/<uuid:event_id>/read/", views.NotificationEventRead.as_view(), name="notification_read"),
    path("inbox/read-all/", views.NotificationReadAll.as_view(), name="notification_read_all"),
    path("staging-receiver/", views.StagingWebhookReceiver.as_view(), name="staging_webhook_receiver"),
]
