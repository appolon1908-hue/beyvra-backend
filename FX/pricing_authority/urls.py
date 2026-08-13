from django.urls import path
from .views import CurrentPlanView, EntitlementsView, PlanListView, TradingPreviewView, TransferPreviewView, WithdrawalPreviewView

urlpatterns = [
 path("plans", PlanListView.as_view()),
 path("pricing/plan", CurrentPlanView.as_view()),
 path("pricing/entitlements", EntitlementsView.as_view()),
 path("entitlements", EntitlementsView.as_view()),
 path("pricing/trading/preview", TradingPreviewView.as_view()),
 path("pricing/withdrawal/preview", WithdrawalPreviewView.as_view()),
 path("pricing/transfer/preview", TransferPreviewView.as_view()),
]
