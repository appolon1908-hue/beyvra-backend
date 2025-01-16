from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from trade.models import Trade
from trade.serializers import TradeSerializer
from users.models import User
import uuid
from django.core.cache import cache
from .constants import ONLINE_COUNT_GROUP

channel_layer = get_channel_layer()

##Used this code to simulate the process of generating and storing tickets for a particular user with their id, so i can pass the custom authentication for the consumers
def generate_and_store_ticket(user_id: int) -> str:
    """
    Generates a unique ticket and stores it in Redis with the user ID.
    
    Args:
        user_id (int): The ID of the user to associate with the ticket.

    Returns:
        str: The generated ticket.
    """
    ticket = str(uuid.uuid4())
    cache.set(ticket, user_id, timeout=None)
    return ticket



@database_sync_to_async
def db_online_users_count() -> int:
    count = User.objects.filter(is_online=True).count()
    count += 1000
    return count


@database_sync_to_async
def db_user_connected(user: User) -> User:
    user.is_online = True
    user.save()
    return user


@database_sync_to_async
def db_user_disconnected(user: User) -> User:
    user.is_online = False
    user.save()
    return user


async def on_connect(channel: AsyncWebsocketConsumer, user: User):
    # this func will run after a user is connected
    await db_user_connected(user)
    # get online users count and update channels
    online_users = await db_online_users_count()
    msg = {
        "type": "send_message",
        "m": ONLINE_COUNT_GROUP,
        "a": "u",
        "d": online_users,
    }
    await channel_layer.group_send(
        ONLINE_COUNT_GROUP,
        msg,
    )


async def on_disconnect(channel: AsyncWebsocketConsumer, user: User):
    await db_user_disconnected(user)
    # get online users count and update channels
    online_users = await db_online_users_count()
    msg = {
        "type": "send_message",
        "m": ONLINE_COUNT_GROUP,
        "a": "u",
        "d": online_users,
    }
    await channel_layer.group_send(
        ONLINE_COUNT_GROUP,
        msg,
    )


@database_sync_to_async
def db_active_trades(user: User) -> list[dict]:
    trades = Trade.objects.filter(is_active=True)
    trades_data = []
    for t in trades:
        trades_data.append(TradeSerializer(t).data)
    return trades_data
