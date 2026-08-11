import logging
from datetime import datetime
from provider_governance.service import resolve_provider
from uuid import UUID

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestBarRequest, CryptoTradesRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    GetAssetsRequest,
    GetCalendarRequest,
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)
from api_trade.utils.alpaca_util import (
    check_timeframe,
    format_orders_to_unix_timestamp,
    format_to_unix_order_dict,
    list_of_lists_to_dict,
    paginate_alpaca_response,
    response_dict_format,
    validate_date_format,
    validate_date_range,
)
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from rest_framework import status


class AlpacaIntegrationAccount:
    """Alpaca integration."""

    restricted_message = "Account is currently restricted from trading."

    def __init__(self):
        self.trading_client = TradingClient(
            settings.API_KEY_ALPACA,
            settings.SECRET_KEY_ALPACA,
        )

    def get_account_info(self):
        """Get account info."""
        account = self.trading_client.get_account()
        if account.trading_blocked:
            raise ValidationError(
                self.restricted_message,
                params={"status": status.HTTP_403_FORBIDDEN},
            )
        # Check how much money we can use to open new positions.
        # print('${} is available as buying power.'.format(account.buying_power))

        return account

    def get_clock(self):
        """Get clock."""
        clock = self.trading_client.get_clock()
        clock = {
            **clock.model_dump(),
            "timestamp": clock.timestamp.timestamp(),
            "next_open": clock.next_open.timestamp(),
            "next_close": clock.next_close.timestamp(),
        }

        return clock

    def get_calendar(self, request):
        """Get calendar."""
        start = request.query_params.get("start", None)
        end = request.query_params.get("end", None)

        resolve_provider(
            provider_id="alpaca_calendar", provider_type="ECONOMIC_CALENDAR",
            product="MARKET_SESSIONS", symbol="*", region="US",
            request_id=request.headers.get("X-Request-ID", ""),
            correlation_id=request.headers.get("X-Correlation-ID", ""),
            caller_service="calendar-api",
        )

        redis_dates_filters = f"calendar_{start}_{end}"
        cached = cache.get(redis_dates_filters)
        if cached:
            logging.info("cached calendar data found. Returning cached data.")
            return cached

        portfolio = self.trading_client.get_calendar(filters=GetCalendarRequest(start=start, end=end))
        portfolio_data = [
            {
                **item.model_dump(),
                "open": item.open.timestamp(),
                "close": item.close.timestamp(),
                "date": (datetime.strptime(item.date.isoformat(), "%Y-%m-%d")).timestamp(),
            }
            for item in portfolio
        ]
        # Cache for 12 hours
        cache.set(redis_dates_filters, portfolio_data, 60 * 60 * 12)

        return portfolio_data


class AlpacaIntegrationDataHistorical:
    """Alpaca integration data."""

    def __init__(self):
        self.client = CryptoHistoricalDataClient()
        # TODO: update to use request_params to filter data
        self.request_params = CryptoBarsRequest(
            symbol_or_symbols=["BTC/USD", "ETH/USD"],
            timeframe=TimeFrame.Hour,
            start="2024-02-13",
        )

    def get_crypto_bars(self, request):
        """Get crypto bars."""
        try:
            symbol_or_symbols = request.query_params.get(
                "symbol_or_symbols",
                None,
            )
            start = request.query_params.get("start", None)
            end = request.query_params.get("end", None)
            time_frame = check_timeframe(
                request.query_params.get("timeframe", None),
            )

            today = datetime.now().strftime("%Y-%m-%d")
            # if today < start:
            #     raise ValidationError(
            #         "Start date is in the future.",
            #         params={"status": status.HTTP_400_BAD_REQUEST},
            #     )
            # if end:
            #     if start > end:
            #         raise ValidationError(
            #             "Start date is greater than end date.",
            #             params={"status": status.HTTP_400_BAD_REQUEST},
            #         )

            # TODO: check if we need to change the time frame
            if today > start and time_frame.value == "1Min":
                time_frame = TimeFrame.Hour

            request_params = CryptoBarsRequest(
                symbol_or_symbols=[symbol_or_symbols],
                timeframe=time_frame,
                start=start,
                end=end,
            )

            key_redis = f"{symbol_or_symbols}_{time_frame}_{start}_{end}"
            cached = cache.get(key_redis)
            if cached:
                logging.info(cached)
                return cached, None

            bars_crypto = self.client.get_crypto_bars(request_params)
            bars_dict = bars_crypto.dict()
            bars_dict = response_dict_format(bars_dict)
            cache.set(key_redis, bars_dict, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

            return bars_dict, None
        except Exception as e:
            logging.error(e)
            return None, e

    def get_crypto_trades(self, request):
        """Get crypto trades."""
        try:
            symbol_or_symbols = request.query_params.get(
                "symbol_or_symbols",
                None,
            )
            limit = request.query_params.get("limit", None)
            start = request.query_params.get("start", None)
            end = request.query_params.get("end", None)

            if end:
                validate_date_format(end)
            if start:
                validate_date_format(start)
                validate_date_range(
                    start,
                    end,
                    datetime.now().strftime("%Y-%m-%d"),
                )

            request_params = CryptoTradesRequest(
                symbol_or_symbols=[symbol_or_symbols],
                start=start,
                end=end,
                limit=limit,
                sort=request.query_params.get("sort", None),
            )

            key_redis = f"{symbol_or_symbols}_{limit}_{start}_{end}"
            cached = cache.get(key_redis)
            if cached:
                logging.info(cached)
                return cached, None

            crypto_trades = self.client.get_crypto_trades(request_params)
            crypto_trades_dict = crypto_trades.dict()
            crypto_trades_dict = response_dict_format(crypto_trades_dict)
            cache.set(key_redis, crypto_trades_dict, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

            return crypto_trades_dict, None
        except Exception as e:
            logging.error(e)
            return None, e

    def get_crypto_latest_bar(self, request):
        """Get crypto latest bar."""
        try:
            symbol_or_symbols = request.query_params.get(
                "symbol_or_symbols",
                None,
            )
            symbol_or_symbols = symbol_or_symbols.split(",")
            request = CryptoLatestBarRequest(symbol_or_symbols=symbol_or_symbols)
            quotes = self.client.get_crypto_latest_bar(request)
            quotes = [
                {
                    **value.model_dump(),
                    "timestamp": value.model_dump()["timestamp"].timestamp(),
                }
                for key, value in quotes.items()
            ]
            return quotes, None
        except Exception as e:
            logging.error(e)
            return None, e

    def get_crypto_latest_quote(self):
        """Get crypto quotes."""

        quotes = self.client.get_crypto_latest_quote(self.request_params)
        return quotes

    def get_crypto_latest_trade(self):
        """Get crypto quotes."""

        quotes = self.client.get_crypto_latest_trade(self.request_params)
        return quotes

    def get_crypto_snapshot(self):
        """Get crypto quotes."""

        quotes = self.client.get_crypto_snapshot(self.request_params)
        return quotes


class AlpacaIntegrationAssets:
    """Alpaca integration assets."""

    def __init__(self):
        self.trading_client = TradingClient(
            settings.API_KEY_ALPACA,
            settings.SECRET_KEY_ALPACA,
        )

    def get_assets(self, request):
        """Get assets."""
        status = request.query_params.get("status", None)
        exchange = request.query_params.get("exchange", None)
        search_params = GetAssetsRequest(
            asset_class=str(request.query_params.get("asset_class", AssetClass.CRYPTO)).lower(),
            status=str(status).lower if status else None,
            exchange=str(exchange).upper() if exchange else None,
        )
        assets = self.trading_client.get_all_assets(filter=search_params)

        paginated_assets = paginate_alpaca_response(assets, request)

        assets = list_of_lists_to_dict(paginated_assets)
        return assets

    def get_asset(self, request):
        """Get asset."""
        try:
            asset = self.trading_client.get_asset(
                request.query_params.get("asset", "AAPL"),
            )
            asset = asset.model_dump()
            return asset, None
        except Exception:
            return None, "External execution request failed"

    def add_asset_to_watchlist_by_id(self, asset_id):
        """Get asset by id."""
        asset = self.trading_client.add_asset_to_watchlist_by_id(asset_id)
        return asset

    def remove_asset_from_watchlist_by_id(self, asset_id):
        """Remove asset from watchlist."""
        asset = self.trading_client.remove_asset_from_watchlist_by_id(asset_id)
        return asset

    def get_watchlists(self):
        """Get watchlist."""
        watchlist = self.trading_client.get_watchlists()
        return watchlist

    def get_watchlist_by_id(self, watchlist_id):
        """Get watchlist by id."""
        watchlist = self.trading_client.get_watchlist_by_id(watchlist_id)
        return watchlist

    def create_watchlist(self, name):
        """Create watchlist."""
        watchlist = self.trading_client.create_watchlist(name)
        return watchlist

    def delete_watchlist_by_id(self, watchlist_id):
        """Delete watchlist by id."""
        watchlist = self.trading_client.delete_watchlist_by_id(watchlist_id)
        return watchlist

    def update_watchlist_by_id(self, watchlist_id, name):
        """Update watchlist by id."""
        watchlist = self.trading_client.update_watchlist_by_id(watchlist_id, name)
        return watchlist


class AlpacaIntegrationOrders:
    """Alpaca integration orders."""

    def __init__(self):
        self.trading_client = TradingClient(
            settings.API_KEY_ALPACA,
            settings.SECRET_KEY_ALPACA,
            paper=True,  # use paper trading environment
        )

    def get_orders(self, request):
        """Get orders."""
        # TODO: update to use request_params to filter orders
        symbols_req = request.query_params.get("symbols", None)
        if symbols_req:
            symbols_req = symbols_req.split(",")

        get_orders_data = GetOrdersRequest(
            status=request.query_params.get("status", "all"),  # noqa
            limit=request.query_params.get("limit", "50"),  # noqa,
            after=request.query_params.get("after", None),
            until=request.query_params.get("until", None),
            direction=request.query_params.get("direction", "desc"),
            side=request.query_params.get("side", None),
            nested=request.query_params.get("nested", True),  # show nested multi-leg orders
            symbols=symbols_req if symbols_req else None,
        )
        orders = self.trading_client.get_orders(filter=get_orders_data)
        orders = list_of_lists_to_dict(orders)
        orders = format_orders_to_unix_timestamp(orders)

        return orders

    def get_order(self, order_id: UUID):
        """Get order."""
        order = self.trading_client.get_order_by_id(order_id)
        order = format_to_unix_order_dict(order.model_dump())
        return order

    def place_order(
        self,
        request_data,
    ):
        """Place order."""
        # preparing market order
        try:
            market_order_data = MarketOrderRequest(
                symbol=str(request_data["symbol"]).upper(),
                qty=float(request_data["qty"]),
                side=request_data["side"],
                time_in_force=request_data["time_in_force"],
            )

            # Market order
            market_order = self.trading_client.submit_order(order_data=market_order_data)  # noqa

            market_order = format_to_unix_order_dict(market_order.model_dump())

            return market_order, None
        except Exception as e:
            logging.error(e)
            return None, e

    def place_limit_order_data(
        self,
        request_data,
    ):
        """Place limit order."""
        # preparing limit order
        try:
            limit_order_data = LimitOrderRequest(
                symbol=str(request_data["symbol"]).upper(),
                limit_price=request_data["limit_price"],
                notional=request_data["notional"],
                side=request_data["side"],
                time_in_force=request_data["time_in_force"],
            )

            # Limit order
            limit_order = self.trading_client.submit_order(
                order_data=limit_order_data,
            )

            limit_order = format_to_unix_order_dict(limit_order.model_dump())

            return limit_order, None
        except Exception as e:
            logging.error(e)
            return None, e

    def cancel_order(self, order_id: UUID):
        """Cancel order."""
        order = self.trading_client.cancel_order_by_id(order_id)
        return order

    def cancel_all_orders(self):
        """Cancel all orders."""
        orders = self.trading_client.cancel_orders()
        orders = list_of_lists_to_dict(orders)
        orders = format_orders_to_unix_timestamp(orders)
        return orders

    def submit_shortsale(self):
        """Submit short sale."""
        market_order_data = MarketOrderRequest(symbol="SPY", qty=1, side=OrderSide.SELL, time_in_force=TimeInForce.GTC)

        # Market order
        market_order = self.trading_client.submit_order(order_data=market_order_data)

        return market_order


class AlpacaIntegrationPositions:
    """Alpaca integration positions."""

    def __init__(self):
        self.trading_client = TradingClient(
            settings.API_KEY_ALPACA,
            settings.SECRET_KEY_ALPACA,
        )

    def get_positions(self):
        """Get positions."""
        positions = self.trading_client.get_all_positions()
        # # Print the quantity of shares for each position.
        # for position in portfolio:
        #     print("{} shares of {}".format(position.qty, position.symbol))
        return positions

    def close_position(self, symbol):
        """Close position."""
        position = self.trading_client.close_position(symbol)
        return position

    def close_all_positions(self):
        """Close all positions."""
        positions = self.trading_client.close_all_positions()
        return positions
