from django.urls import path

from . import views

urlpatterns = [
    path("safety-flags", views.SafetyFlags.as_view()),
    path("accounts/<int:account_id>/freeze", views.OperatorFreeze.as_view()),
    path("actions/<uuid:request_id>/approve", views.OperatorApprove.as_view()),
]
