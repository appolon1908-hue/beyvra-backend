from django.urls import path

from . import views

urlpatterns = [
    path("dashboard-metrics/", views.dashboard_metrics, name="dashboard_metrics"),
]
