from django.urls import path
from .api import *

urlpatterns = [
    path("accounts", AccountsView.as_view()),
    path("cash", CashView.as_view()), path("cash/<str:currency>", CashView.as_view()),
    path("liquidity", LiquidityView.as_view()), path("liquidity/<str:currency>", LiquidityView.as_view()),
    path("collateral", CollateralView.as_view()), path("collateral/<str:asset>", CollateralView.as_view()),
    path("collateral/mobility/preview", MobilityPreviewView.as_view()),
    path("funding-requirements", FundingRequirementsView.as_view()), path("funding-requirements/<uuid:requirement_id>", FundingRequirementsView.as_view()),
    path("intraday", IntradayView.as_view()), path("intraday/<str:currency>", IntradayView.as_view()),
    path("forecast", ForecastView.as_view()), path("forecast/<str:currency>", ForecastView.as_view()),
    path("transfer-plans/preview", TransferPlanPreviewView.as_view()), path("transfer-plans", TransferPlansView.as_view()), path("transfer-plans/<uuid:plan_id>", TransferPlansView.as_view()),
    path("settlement-funding", SettlementFundingView.as_view()), path("settlement-funding/<str:settlement_id>", SettlementFundingView.as_view()),
    path("stress/preview", StressPreviewView.as_view()), path("reconciliation/status", ReconciliationStatusView.as_view()),
]
