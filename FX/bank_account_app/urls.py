from django.urls import path

from . import views

urlpatterns = [
    path("", views.BankAccountView.as_view(), name="bank-account"),
    path("tradxio/", views.AdminBankAccountView.as_view(), name="admin-bank-account"),
    
]
