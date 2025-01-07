from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..scripts.alpaca_trade_api import AlpacaMarketData


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="top",
            type=OpenApiTypes.INT,
            default=10,
        ),
        OpenApiParameter(
            name="market_type",
            type=OpenApiTypes.STR,
            default="crypto",
            enum=["stocks", "crypto"],
        ),
    ],
)
@api_view(["GET"])
def get_market_movers(request):
    """
    Returns the top market movers (gainers and losers). The change for each symbol is calculated
        from the previous closing price and the latest closing price.

        For stocks the endpoint resets at market open, until then it shows the last market day's movers.
        The data is split adjusted. Only tradable symbols are included.

        For crypto the endpoint resets at midnight.
    """
    alpaca = AlpacaMarketData()
    response = alpaca.get_market_movers(request)
    return Response(response)
