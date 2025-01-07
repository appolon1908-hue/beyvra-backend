from rest_framework import serializers


# Serializer
class CryptoBarsSerializer(serializers.Serializer):
    symbol = serializers.CharField(required=True)
    timeframe = serializers.CharField()
    start = serializers.DateField()


class OrderSerializer(serializers.Serializer):
    """Order serializer.

    Attributes:
    symbol (str): The symbol identifier for the asset being traded
    qty (Optional[float]): The number of shares to trade. Fractional qty for stocks only with market orders.
    notional (Optional[float]): The base currency value of the shares to trade. For stocks, only works with MarketOrders.
        **Does not work with qty**.
    side (OrderSide): Whether the order will buy or sell the asset.
    # type (OrderType): The execution logic type of the order (market, limit, etc).
    time_in_force (TimeInForce): The expiration logic of the order.
    extended_hours (Optional[float]): Whether the order can be executed during regular market hours.
    client_order_id (Optional[str]): A string to identify which client submitted the order.
    order_class (Optional[OrderClass]): The class of the order. Simple orders have no other legs.
    take_profit (Optional[TakeProfitRequest]): For orders with multiple legs, an order to exit a profitable trade.
    stop_loss (Optional[StopLossRequest]): For orders with multiple legs, an order to exit a losing trade.
    """  # noqa

    symbol = serializers.CharField(required=True, max_length=25)
    qty = serializers.FloatField(required=False)
    side = serializers.ChoiceField(choices=["buy", "sell"])
    notional = serializers.FloatField(required=False, default=None)
    # type = serializers.ChoiceField(
    #     choices=[
    #         "market",
    #         "limit",
    #         "stop",
    #         "stop_limit",
    #         "trailing_stop",
    #     ],
    #     required=False,
    # )
    time_in_force = serializers.ChoiceField(
        choices=[
            "day",
            "gtc",
            "opg",
            "ioc",
            "fok",
            "cls",
        ]
    )
    order_class = serializers.ChoiceField(
        choices=[
            "simple",
            "bracket",
            "oco",
            "oto",
        ],
    )
    extended_hours = serializers.BooleanField(default=False)
    client_order_id = serializers.CharField(required=False, max_length=125, default=None)
    take_profit = serializers.FloatField(required=False, default=None)
    stop_loss = serializers.FloatField(required=False, default=None)
    limit_price = serializers.FloatField(required=False, default=None)


class OrderIdSerializer(serializers.Serializer):
    """Order ID serializer.

    Attributes:
    order_id (str): The unique identifier of the order.
    """

    order_id = serializers.CharField(required=True, max_length=25)


class TrailingStopOrderRequestSerializer(OrderSerializer):
    """Trailing stop order serializer.

    Attributes:
    trail_price (float): The price distance between the stop price and the current market price.
    trail_percent (Optional[float]): The percent price difference by which the trailing stop will trail.
    """

    trail_price = serializers.FloatField(required=False, default=0.0)
    trail_percent = serializers.FloatField(required=False, default=0.0)


class NewsAlpacaSerializer(serializers.Serializer):
    """News Alpaca serializer.

    - Attributes:
        * ```symbol``` (str): The symbol identifier for the asset being traded
        * ```start``` (str): The start date for the data.
        * ```end``` (str): The end date for the data.
        * ```sort``` (str): The sort order for the data.
        * ```include_content``` (bool): Whether to include the content in the data.
        * ```exclude_contentless``` (bool): Whether to exclude contentless data.
    """

    symbol = serializers.CharField(required=True, max_length=25)
    include_content = serializers.BooleanField(default=True)
    exclude_contentless = serializers.BooleanField(default=True)
    start = serializers.DateField()
    end = serializers.DateField()
    sort = serializers.ChoiceField(choices=["asc", "desc"], default="desc")


class GetListOrdersSerializer(serializers.Serializer):
    """Get list orders serializer.

    - Attributes:
        * ```status``` (str): The status of the orders.
        * ```limit``` (int): The number of orders to return.
        * ```after``` (str): The start of the time range.
        * ```until``` (str): The end of the time range.
        * ```direction``` (str): The direction of the orders.
    """

    status = serializers.ChoiceField(choices=["open", "closed", "all"], default="open")
    limit = serializers.IntegerField(default=50)
    after = serializers.DateField(required=False)
    until = serializers.DateField(required=False)
    direction = serializers.ChoiceField(choices=["asc", "desc"], default="desc")
