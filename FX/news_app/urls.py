from django.urls import path

from . import views

urlpatterns = [
    path("", views.get_news_newsdata, name="newsdata"),
   path("<str:article_id>/", views.get_news_by_id, name="newsdata_by_id"),
]
