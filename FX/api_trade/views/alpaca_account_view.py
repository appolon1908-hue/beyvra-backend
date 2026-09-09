from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from provider_governance.service import ProviderNotAvailable

from ..scripts.alpaca_integration import AlpacaIntegrationAccount


@api_view(["GET"])
def get_clock_view(request):
    """Return the current market clock from the governed provider."""
    result = AlpacaIntegrationAccount().get_clock()
    return Response(result)


class GetCalendarViewSet(viewsets.ViewSet):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start",
                required=True,
                type=OpenApiTypes.DATE,
                description="First market date. Supply an ISO 8601 date (YYYY-MM-DD).",
            ),
            OpenApiParameter(
                name="end",
                required=False,
                type=OpenApiTypes.DATE,
                description="Optional last market date in ISO 8601 format (YYYY-MM-DD).",
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
        try:
            result = AlpacaIntegrationAccount().get_calendar(request)
        except ProviderNotAvailable:
            return Response(
                {"code": "PROVIDER_NOT_AVAILABLE"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(result)
