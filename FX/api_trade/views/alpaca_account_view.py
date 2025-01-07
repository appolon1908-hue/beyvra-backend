from datetime import datetime

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..scripts.alpaca_integration import AlpacaIntegrationAccount


@api_view(["GET"])
def get_clock_view(request):
    """Gets the current market timestamp, whether or not the market is
    currently open, as well as the times of the next market open and close"""
    result = AlpacaIntegrationAccount().get_clock()

    return Response(result)


class GetCalendarViewSet(viewsets.ViewSet):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start",
                required=True,
                type=OpenApiTypes.DATE,
                default=datetime.now().strftime("%Y-%m-%d"),
            ),
            OpenApiParameter(
                name="end",
                required=False,
                type=OpenApiTypes.DATE,
            ),
        ],
    )
    def list(self, request):
        """
        Get calendar.
        The calendar API serves the full list of market days from 1970 to 2029.
        It can also be queried by specifying a start and/or end time to narrow down the results.
        In addition to the dates, the response also contains the specific open and close times for
        the market days, taking into account early closures.

        Returns the market calendar.
        """
        result = AlpacaIntegrationAccount().get_calendar(request)

        return Response(result)
