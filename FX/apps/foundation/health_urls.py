from django.urls import path

from .health import live, ready

urlpatterns = [path("live", live), path("ready", ready)]
