from django.urls import path

from . import views

urlpatterns = [
    path("stripe_checkout/", views.StripeCheckoutView.as_view(), name="stripe_checkout"),
    path("stripe_webhook/", views.StripeWebhook.as_view(), name="stripe_webhook"),
    path("binance_pay/", views.BinancePay.as_view(), name="binance_pay"),
    path("methods/", views.PaymentMethodList.as_view(), name="payment_methods"),
    path("", views.PaymentView.as_view(), name="payment"),

]
