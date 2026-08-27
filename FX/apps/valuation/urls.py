from django.urls import path
from .api import CostBasis, Disabled, Lots, Nav, Prices, Realized, Unrealized
from .portfolio_api import (
 PortfolioAllocationsView,
 PortfolioEvidenceQualityView,
 PortfolioPerformanceView,
 PortfolioPositionsView,
 PortfolioRiskView,
 PortfolioSummaryView,
)
urlpatterns=[
 path("valuation/prices/<str:instrument_id>/history",Prices.as_view()),path("valuation/prices/<str:instrument_id>",Prices.as_view()),
 path("valuation/positions",Disabled.as_view()),path("valuation/positions/<str:instrument_id>",Disabled.as_view()),path("valuation/nav",Nav.as_view()),path("valuation/nav/history",Nav.as_view()),
 path("pnl/unrealized",Unrealized.as_view()),path("pnl/unrealized/<str:instrument_id>",Unrealized.as_view()),path("pnl/realized",Realized.as_view()),path("pnl/realized/<str:instrument_id>",Realized.as_view()),
 path("cost-basis",CostBasis.as_view()),path("cost-basis/<str:instrument_id>",CostBasis.as_view()),path("tax-lots",Lots.as_view()),path("tax-lots/<uuid:lot_id>",Lots.as_view()),path("tax-lots/selection/preview",Disabled.as_view()),
 path("valuation/fx",Disabled.as_view()),path("valuation/fx/<str:base>/<str:quote>",Disabled.as_view()),path("performance",Disabled.as_view()),path("performance/history",Disabled.as_view()),path("performance/attribution",Disabled.as_view()),
 path("valuation/reconciliation/status",Disabled.as_view()),path("valuation/snapshots",Disabled.as_view()),path("valuation/snapshots/<uuid:snapshot_id>",Disabled.as_view()),
 path("portfolio/summary",PortfolioSummaryView.as_view()),path("portfolio/positions",PortfolioPositionsView.as_view()),path("portfolio/performance",PortfolioPerformanceView.as_view()),path("portfolio/allocations",PortfolioAllocationsView.as_view()),path("portfolio/risk",PortfolioRiskView.as_view()),path("portfolio/evidence-quality",PortfolioEvidenceQualityView.as_view()),
]
