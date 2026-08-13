from django.urls import path
from .api import live
urlpatterns=[path("",live,name="platform_health")]
