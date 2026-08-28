import logging

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import TrailingStopOrderRequest
from api_trade.utils.alpaca_util import format_to_unix_order_dict
from django.conf import settings


def _trading_client():
    return TradingClient(
        settings.API_KEY_ALPACA,
        settings.SECRET_KEY_ALPACA,
        paper=settings.TRADING_MODE == "paper",
        url_override=settings.ALPACA_TRADING_BASE_URL,
    )


class AlpacaTrailingStopOrder:
    """Alpaca trailing orders."""

    def __init__(self):
        self.trading_client = _trading_client()

    def place_trail_order(self, request_data):
        """Trail order."""
        try:
            trail_order_data = TrailingStopOrderRequest(
                symbol=str(request_data["symbol"]).upper(),
                notional=(request_data["notional"] if request_data["notional"] not in [None, ""] else None),
                qty=(request_data["qty"] if request_data["qty"] not in [None, ""] else None),
                side=request_data["side"],
                time_in_force=request_data["time_in_force"],
                extended_hours=request_data["extended_hours"],
                client_order_id=(
                    request_data["client_order_id"] if request_data["client_order_id"] not in [None, ""] else None
                ),
                order_class=request_data["order_class"],
                take_profit=(request_data["take_profit"] if request_data["take_profit"] not in [None, ""] else None),
                stop_loss=(request_data["stop_loss"] if request_data["stop_loss"] not in [None, ""] else None),
                trail_price=(request_data["trail_price"] if request_data["trail_price"] not in [None, ""] else None),
                trail_percent=(
                    request_data["trail_percent"] if request_data["trail_percent"] not in [None, ""] else None
                ),
            )

            order = self.trading_client.submit_order(
                order_data=trail_order_data,
            )
            order = format_to_unix_order_dict(order.model_dump())
            return order, None
        except Exception as e:
            logging.error(e)
            return None, e
