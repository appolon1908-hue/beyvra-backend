from uuid import UUID

from api_trade.serializers import OrderSerializer
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..scripts.alpaca_integration import AlpacaIntegrationOrders


class AlpacaOrdersViewSet(viewsets.ViewSet):
    """
    ViewSet to handle Alpaca orders.
    """

    serializer_class = OrderSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="symbol_or_symbols",
                required=False,
                type=OpenApiTypes.STR,
                description="```The symbol or symbols separated by coma.```",
            ),
            OpenApiParameter(
                name="status",
                required=False,
                type=OpenApiTypes.STR,
                description="```Order status to be queried. open, closed or all```. Defaults to open.",
                enum=["open", "closed", "all"],
                default="open",
            ),
            OpenApiParameter(
                name="limit",
                required=False,
                type=OpenApiTypes.INT,
                description="```The maximum number of orders to return```. Defaults to 50 and max is 500.",
                default=50,
            ),
            OpenApiParameter(
                name="after",
                required=False,
                type=OpenApiTypes.STR,
                description="```The response will include only ones submitted after this timestamp.``` Example: 2024-02-03",  # noqa
            ),
            OpenApiParameter(
                name="until",
                required=False,
                type=OpenApiTypes.STR,
                description="```The response will include only ones submitted until this timestamp.``` Example: 2024-02-03",  # noqa
            ),
            OpenApiParameter(
                name="direction",
                required=False,
                type=OpenApiTypes.STR,
                description="```The chronological order of the returned items.``` Defaults to desc.",
                enum=["asc", "desc"],
                default="desc",
            ),
            OpenApiParameter(
                name="nested",
                required=False,
                type=OpenApiTypes.BOOL,
                description="```Filters down to orders that have a matching side field set.```",
                default=False,
            ),
            OpenApiParameter(
                name="side",
                required=False,
                type=OpenApiTypes.STR,
                description="```The order id to be queried.```",
                enum=["buy", "sell"],
                default="buy",
            ),
        ],
    )
    def list(self, request):
        """
        Return a list of all orders.
        """
        result = AlpacaIntegrationOrders().get_orders(request)
        return Response(result)

    def create(self, request):
        """
        Create a new order.
        """
        result, e = AlpacaIntegrationOrders().place_order(request.data)
        if result is None:
            return Response({"error": f"{e}"}, status=400)
        return Response(result)

    def retrieve(self, request, order_id: UUID = None):
        """
        Retrieve a specific order by ID.
        """
        try:
            result = AlpacaIntegrationOrders().get_order(order_id=order_id)
            return Response(result)
        except ValueError as e:
            return Response({"error": f"{e}"}, status=400)

    def destroy(self, request, order_id: UUID = None):
        """
        Delete an order by id.
        """
        try:
            result = AlpacaIntegrationOrders().cancel_order(order_id)
            return Response(result, status=status.HTTP_204_NO_CONTENT)

        except ValueError as e:
            return Response({"error": f"{e}"}, status=400)

    @action(detail=False, methods=["delete"])
    def cancel_all(self, request):
        """
        Cancel all orders.
        """
        result = AlpacaIntegrationOrders().cancel_all_orders()
        return Response(result)
