from django.urls import path
from apps.valuation.portfolio_api import PortfolioSummaryView

from .views import CryptoMarketDataView, StockMarketDataView, AssetView, CreateAssetView, TotalBalanceView, TotalProfitLossView

app_name = "portfolio"

urlpatterns = [
    path("summary/", PortfolioSummaryView.as_view(), name="summary"),
    path("crypto-market-data/", CryptoMarketDataView.as_view(), name="crypto-market-data"),
    path("stock-market-data/", StockMarketDataView.as_view(), name="stock-market-data"),
    path("asset/<int:id>/", AssetView.as_view(), name="asset"),
    path("asset/create/", CreateAssetView.as_view(), name="create-asset"),
    path("total-balance/", TotalBalanceView.as_view(), name="total-balance"),
    path("total-profit-loss/", TotalProfitLossView.as_view(), name="total-profit-loss"),
]
