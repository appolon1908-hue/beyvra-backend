from django.urls import path

from .api import Disabled

urlpatterns = [
    path("prices", Disabled.as_view()),
    path("reconciliation", Disabled.as_view()),
    path("reconciliation/run", Disabled.as_view()),
]
