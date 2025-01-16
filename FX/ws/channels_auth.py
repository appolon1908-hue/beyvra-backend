from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from users.models import User


@database_sync_to_async
def get_user(user_id: int) -> User:
    try:
        user = User.objects.get(id=user_id)
        return user
    except User.DoesNotExist:
        return AnonymousUser()


class CustomTokenAuthMiddleware(BaseMiddleware):
    """
    Authentication middleware for channels
    """

    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        """Checks if a 'ticket' query param is in the header and authorize a user

        Returns:
            User: django user
        """
        # TODO: make only one socket connection per client
        # if a user logs in another device invalidate the other sockets

        # get ticket from query param
        query_string = scope["query_string"].decode("utf-8")
        query_params = dict(parse_qs(query_string))
        ws_ticket = query_params.get("ws_ticket")[0]
        # get user id from redis cache
        user_id = cache.get(ws_ticket, None)
        # delete ticket to make it accessible by one user only
        cache.delete(ws_ticket)
        if user_id is None:
            scope["user"] = AnonymousUser()
        else:
            scope["user"] = await get_user(user_id)

        return await super().__call__(scope, receive, send)
