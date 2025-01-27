from django.urls import path
from tickets import views

urlpatterns = [
    path("tickets/", views.GetTicketView.as_view(), name="get_ticket"),
]
