import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import django
from alpaca.data.live import CryptoDataStream
from channels.layers import get_channel_layer

BASE_DIR = Path("/app")
sys.path.append(os.path.join(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FX.settings")

from django.conf import settings  # noqa
from fx_utils.constants import DATE_FORMAT  # noqa

# Only necessary if using Django standalone scripts
if not settings.configured:
    django.setup()


from api_trade.scripts.utils import get_mock_bar_data  # noqa
from ws.constants import BARS_DATA_GROUP  # noqa

channel_layer = get_channel_layer()

logging.basicConfig(level=logging.INFO)

# Referance for supported crypto
# https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support

CRYPTO_SYMBOLS = [
    "AAVE/USD",
    "AVAX/USD",
    "BAT/USD",
    "BCH/USD",
    "BTC/USD",
    "CRV/USD",
    "DOT/USD",
    "ETH/USD",
    "GRT/USD",
    "LINK/USD",
    "LTC/USD",
    "MKR/USD",
    "SHIB/USD",
    "UNI/USD",
    "USDC/USD",
    "USDT/USD",
    "XTZ/USD",
    # "AAVE/USDC",
    # "AVAX/USDC",
    # "BAT/USDC",
    # "BCH/USDC",
    # "BTC/USDC",
    # "CRV/USDC",
    # "DOT/USDC",
    # "ETH/USDC",
    # "GRT/USDC",
    # "LINK/USDC",
    # "LTC/USDC",
    # "MKR/USDC",
    # "SHIB/USDC",
    # "UNI/USDC",
    # "XTZ/USDC",
    # "AAVE/USDT",
    # "BCH/USDT",
    # "BTC/USDT",
    # "ETH/USDT",
    # "LINK/USDT",
    # "LTC/USDT",
    # "UNI/USDT",
    # "BCH/BTC",
    # "ETH/BTC",
    # "LTC/BTC",
    # "UNI/BTC",
]


def run_fetch_data():
    """Subscribing to Real-Time Quote Data"""
    logging.info("Initializing...")
    api_key_alpaca = os.getenv("API_KEY_ALPACA")
    secret_key_alpaca = os.getenv("API_SECRET_ALPACA")
    logging.info("Getting WSS Client...")
    wss_client = CryptoDataStream(
        api_key_alpaca,
        secret_key_alpaca,
    )
    try:

        async def quotes_data_handler(data):
            data = data.dict()
            data["timestamp"] = data["timestamp"].timestamp()
            # logging.info(f"Quote: {data}")
            room_name = data["symbol"].replace("/", "_")
            await channel_layer.group_send(room_name, {"type": "quote_data", "data": data})

        async def bars_data_handler(data):
            data = data.dict()
            data["timestamp"] = data["timestamp"].timestamp()
            # logging.info(f"Bar: {data}")
            room_name = data["symbol"].replace("/", "_")
            await channel_layer.group_send(room_name, {"type": "bars_data", "data": data})

        logging.info("Subscribing to bars data...")
        for symbol in CRYPTO_SYMBOLS:
            wss_client.subscribe_quotes(quotes_data_handler, symbol)
            wss_client.subscribe_bars(bars_data_handler, symbol)
        wss_client.run()
    except KeyboardInterrupt:
        wss_client.close()
    except Exception as e:
        logging.error(f"Error: {e}")
        wss_client.close()


async def run_fake_fetch_data():
    bars = get_mock_bar_data()
    symbol = "BTC"
    size = len(bars[symbol]) - 1
    i = 1
    while True:
        i_temp = i % size
        d = bars[symbol][i_temp]
        now = datetime.now()
        bar_data = {
            "s": symbol,
            "t": now.strftime(DATE_FORMAT),
            "o": float(d[1]),
            "h": float(d[2]),
            "l": float(d[3]),
            "c": float(d[4]),
        }
        # ws update message
        update_room = {
            "type": "send_message",
            "m": BARS_DATA_GROUP,
            "a": "c",
            "d": [bar_data],
        }
        # logging.info(f"Bar: {update_room}")
        await channel_layer.group_send(
            symbol,
            update_room,
        )
        i += 1
        await asyncio.sleep(1)


if __name__ == "__main__":
    # run_fetch_data()
    asyncio.get_event_loop().run_until_complete(run_fake_fetch_data())
    run_fake_fetch_data()
