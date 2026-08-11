from django.urls import path
from .views import *
urlpatterns=[
 path("risk/summary",SummaryView.as_view()), path("risk/margin/preview",MarginPreview.as_view()), path("risk/margin/requirements",FeatureDisabledView.as_view()), path("risk/margin/policies/current",FeatureDisabledView.as_view()),
 path("risk/collateral",FeatureDisabledView.as_view()),path("risk/collateral/preview",CollateralPreview.as_view()),path("risk/collateral/<str:asset>",FeatureDisabledView.as_view()),
 path("risk/buying-power",FeatureDisabledView.as_view()),path("risk/buying-power/preview",BuyingPowerPreview.as_view()),path("risk/exposure",FeatureDisabledView.as_view()),path("risk/exposure/limits",FeatureDisabledView.as_view()),path("risk/exposure/preview",ExposurePreview.as_view()),
 path("risk/margin-health",MarginHealthView.as_view()),path("risk/margin-calls",MarginCallsView.as_view()),path("risk/margin-calls/<uuid:call_id>",MarginCallsView.as_view()),path("risk/liquidation/status",FeatureDisabledView.as_view()),path("risk/liquidation/preview",LiquidationPreview.as_view()),
 path("risk/portfolio",SummaryView.as_view()),path("risk/positions",FeatureDisabledView.as_view()),path("risk/positions/<uuid:instrument_id>",FeatureDisabledView.as_view()),
 path("operator/risk/margin/policies",FeatureDisabledView.as_view()),path("operator/risk/collateral/policies",FeatureDisabledView.as_view()),path("operator/risk/exposure/limits",FeatureDisabledView.as_view()),path("operator/risk/margin-calls",FeatureDisabledView.as_view()),path("operator/risk/liquidations",FeatureDisabledView.as_view()),
]
