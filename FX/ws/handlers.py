from datetime import datetime, timedelta

from api_trade.scripts.utils import get_mock_bar_data
from channels.generic.websocket import AsyncWebsocketConsumer
from fx_utils.constants import DATE_FORMAT

from .constants import INIT_BARS_GROUP, ONLINE_COUNT_GROUP, TRADE_GROUP
from .utils import db_active_trades, db_online_users_count


async def join_group_handler(channel: AsyncWebsocketConsumer, data: dict):
    user = channel.scope["user"]
    group_name = data["group_name"]
    await channel.channel_layer.group_add(group_name, channel.channel_name)
    channel.groups.append(group_name)
    # TODO: refactor and handle it separately
    if group_name == ONLINE_COUNT_GROUP:
        online_users = await db_online_users_count()
        msg = {
            "type": "send_message",
            "m": ONLINE_COUNT_GROUP,
            "a": "u",
            "d": online_users,
        }
        await channel.send_message(msg)
    # for b_d group send active trades
    if group_name == "BTC":
        active_trades = await db_active_trades(user)
        msg = {
            "type": "send_message",
            "m": TRADE_GROUP,
            "a": "c",
            "d": active_trades,
        }
        await channel.send_message(msg)


async def leave_group_handler(channel: AsyncWebsocketConsumer, data: dict):
    group_name = data["group_name"]
    await channel.channel_layer.group_discard(group_name, channel.channel_name)
    channel.groups.remove(group_name)


async def init_bars_data_handler(channel: AsyncWebsocketConsumer, data: dict):
    """Send initial bar datas for a specific symbol

    Args:
        channel (AsyncWebsocketConsumer): _description_
        data (dict): _description_
    """
    symbol = data["group_name"]
    symbol = "BTC"
    bars = get_mock_bar_data()[symbol]
    # timestamp should be within 1 second difference
    size = len(bars)
    init_time = datetime.now() - timedelta(seconds=size)
    serialized_bar_data = []

    for i, bar in enumerate(bars):
        t = init_time + timedelta(seconds=i)
        temp_data = {
            "s": symbol,
            "t": t.strftime(DATE_FORMAT),
            "o": float(bar[1]),
            "h": float(bar[2]),
            "l": float(bar[3]),
            "c": float(bar[4]),
        }
        serialized_bar_data.append(temp_data)
    msg = {
        "type": "send_message",
        "m": INIT_BARS_GROUP,
        "a": "c",
        "d": [{symbol: serialized_bar_data}],
    }
    await channel.send_message(msg)


async def received_msg_handler(channel: AsyncWebsocketConsumer, data: dict):
    """Websocket received message handler

    Args:
        channel (AsyncWebsocketConsumer): _description_
        data (dict): _description_
    """
    # dict of received message handler functions
    handlers = {
        "join_group": join_group_handler,
        "leave_group": leave_group_handler,
        "init_bars_data": init_bars_data_handler,
    }
    msg_type = data["type"]
    handler = handlers.get(msg_type, None)
    # if handler function exists handle message
    if handler is not None:
        await handler(channel, data)
