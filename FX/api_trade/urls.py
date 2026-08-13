from api_trade.views import alpaca_position_view  # noqa: F401
from api_trade.views import (
    alpaca_account_view,
    alpaca_assets_view,
    alpaca_historical,
    alpaca_market_data_view,
    alpaca_news_view,
    alpaca_order_view,
    alpaca_trail_order,
)
from django.urls import path
from django.conf import settings
from rest_framework import routers

router = routers.DefaultRouter()


app_name = "api_trade"

urlpatterns = [
    path(
        "market-data/alpaca/",
        alpaca_historical.GetCryptoBarsViewSet.as_view({"get": "list"}),
        name="historical-data",
    ),
    path("assets/", alpaca_assets_view.get_assets, name="assets"),
    path(
        "orders/",
        alpaca_order_view.AlpacaOrdersViewSet.as_view(
            {"get": "list", "post": "create", "delete": "cancel_all"},
        ),
        name="orders",
    ),
    path(
        "orders/detail/<str:order_id>/",
        alpaca_order_view.AlpacaOrdersViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="orders-detail",
    ),
    path(
        "get-clock/",
        alpaca_account_view.get_clock_view,
        name="accounts",
    ),
    path(
        "get-calendar/",
        alpaca_account_view.GetCalendarViewSet.as_view({"get": "list"}),
        name="calendar",
    ),
    path(
        "top-market-movers/",
        alpaca_market_data_view.get_market_movers,
        name="most-actives",
    ),
    path(
        "get-crypto-lates-bars/",
        alpaca_historical.GetCryptoLatestBarsViewSet.as_view({"get": "list"}),
        name="latest-bars",
    ),
    path(
        "trail-order/",
        alpaca_trail_order.AlpacaTrailOrderViewSet.as_view({"post": "create"}),
        name="trail-order",
    ),
    path(
        "get-news/",
        alpaca_news_view.get_news_alpaca,
        name="news",
    ),
    path("get-assets/", alpaca_assets_view.get_asset, name="assets"),
]

# Paper deployments expose read-only market data but never broker order routes.
if (
    settings.PAPER_TRADING_ONLY
    or not settings.REAL_TRADING_ENABLED
    or not settings.EXTERNAL_EXECUTION_ENABLED
    or not settings.REAL_MONEY_ENABLED
):
    urlpatterns = [
        route for route in urlpatterns
        if route.name not in {"orders", "orders-detail", "trail-order"}
    ]
