from api_trade.serializers import TrailingStopOrderRequestSerializer
from rest_framework import status, viewsets
from rest_framework.response import Response

from ..scripts.alpaca_trailing_order import AlpacaTrailingStopOrder


class AlpacaTrailOrderViewSet(viewsets.ViewSet):
    """Alpaca trailing order view set."""

    serializer_class = TrailingStopOrderRequestSerializer

    def create(self, request):
        """
        - Used to submit a trailing stop orders.
        - In terms of asset types, trailing stop orders are typically supported for:

            * Stocks: Most online brokerages allow trailing stop orders for stocks. This includes Alpaca, which supports trailing stop orders for equity trading.

            * Forex: Many forex trading platforms support trailing stop orders. This can be a valuable tool given the 24/7 nature of the forex market.

            * Futures: Trailing stop orders can also be used in futures trading on many platforms.

            * ETFs (Exchange Traded Funds): Just like stocks, trailing stop orders can be placed on ETFs.


        - Attributes:
            * ```symbol``` (str): The symbol identifier for the asset being tradedlike Stocks, Forex and ETFs (e.g. stock symbol can be AAPL).
            * ```qty``` (Optional[float]): The number of shares to trade. Fractional qty for stocks only with market orders.
            * ```notional``` (Optional[float]): The base currency value of the shares to trade. For stocks, only works with MarketOrders.
                **Does not work with qty**.
            * ```side``` (OrderSide): Whether the order will buy or sell the asset.
            * ```time_in_force``` (TimeInForce): The expiration logic of the order.
            * ```extended_hours``` (Optional[float]): Whether the order can be executed during regular market hours.
            * ```client_order_id``` (Optional[str]): A string to identify which client submitted the order.
            * ```order_class``` (Optional[OrderClass]): The class of the order. Simple orders have no other legs.
            * ```take_profit``` (Optional[TakeProfitRequest]): For orders with multiple legs, an order to exit a profitable trade.
            * ```stop_loss``` (Optional[StopLossRequest]): For orders with multiple legs, an order to exit a losing trade.
            * ```trail_price``` (Optional[float]): The absolute price difference by which the trailing stop will trail.
            * ```trail_percent``` (Optional[float]): The percent price difference by which the trailing stop will trail.

        """  # noqa
        result, e = AlpacaTrailingStopOrder().place_trail_order(request.data)
        if result is None:
            return Response(
                {"error": f"{e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)
