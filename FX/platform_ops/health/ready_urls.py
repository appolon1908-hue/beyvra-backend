from django.urls import path
from .api import ready
urlpatterns=[path("",ready,name="platform_ready")]
