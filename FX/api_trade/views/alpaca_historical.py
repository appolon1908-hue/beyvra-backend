from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from ..scripts.alpaca_integration import AlpacaIntegrationDataHistorical


class GetCryptoBarsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    ViewSet to handle Alpaca historical data.
    http://localhost:8000/api/alpaca/?symbol_or_symbols=BTC/USD&start=2024-02-13
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="symbol_or_symbols",
                required=True,
                type=OpenApiTypes.STR,
                default="BTC/USD",
            ),
            OpenApiParameter(
                name="start",
                required=True,
                type=OpenApiTypes.DATE,
                default="2024-02-13",
            ),
            OpenApiParameter(
                name="end",
                required=False,
                type=OpenApiTypes.DATE,
            ),
            OpenApiParameter(
                name="timeframe",
                required=False,
                type=OpenApiTypes.STR,
                enum=[
                    "minute",
                    "hour",
                    "day",
                    "week",
                    "month",
                ],
                default="day",
            ),
        ],
    )
    def list(self, request):
        """
        Return a list of all historical data.
        The crypto bars API provides historical aggregates for a list of crypto symbols between the specified dates.
        """

        result, error_message = AlpacaIntegrationDataHistorical().get_crypto_bars(request)
        if result is None:
            return Response({"error": f"{error_message}"}, status=400)
        return Response(result)


class GetCryptoTradesViewSet(viewsets.ViewSet):
    """
    ViewSet to handle Alpaca historical data.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="symbol_or_symbols",
                required=True,
                type=OpenApiTypes.STR,
                default="BTC/USD",
                description="The ticker identifier or list of ticker identifiers.",
            ),
            OpenApiParameter(
                name="start",
                required=False,
                type=OpenApiTypes.DATE,
                description="The beginning of the time interval for desired data. Timezone naive inputs assumed to be in UTC.",  # noqa
            ),
            OpenApiParameter(
                name="end",
                required=False,
                type=OpenApiTypes.DATE,
                description="The end of the time interval for desired data. Defaults to now. Timezone naive inputs assumed to be in UTC",  # noqa
            ),
            OpenApiParameter(
                name="limit",
                required=False,
                type=OpenApiTypes.INT,
                description="Upper limit of number of data points to return. Defaults to None.",
            ),
            OpenApiParameter(
                name="sort",
                required=False,
                enum=["asc", "desc"],
                description="The chronological order of response based on the timestamp. Defaults to ASC.",
            ),
        ],
    )
    def list(self, request):
        """
        Return a list of all crypto trades.
        """

        result, error_message = AlpacaIntegrationDataHistorical().get_crypto_trades(
            request,
        )
        if result is None:
            return Response({"error": f"{error_message}"}, status=400)
        return Response(result)


class GetCryptoLatestBarsViewSet(viewsets.ViewSet):
    """
    ViewSet to handle Alpaca historical data.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="symbol_or_symbols",
                required=True,
                type=OpenApiTypes.STR,
                default="BTC/USD",
                description="The ticker identifier or list of ticker identifiers.",
            )
        ],
    )
    def list(self, request):
        """
        Return a list of all latest crypto bars.
        The latest multi bars endpoint returns the latest minute-aggregated historical
        bar data for each of the crypto symbols provided.
        """

        result, error_message = AlpacaIntegrationDataHistorical().get_crypto_latest_bar(
            request,
        )
        if result is None:
            return Response({"error": f"{error_message}"}, status=400)
        return Response(result)
