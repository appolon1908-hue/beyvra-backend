from channels.db import database_sync_to_async
from users.models import User
from django.db.models import Count, Q
from django.core.cache import cache
import uuid
import logging

logger = logging.getLogger(__name__)


@database_sync_to_async
def db_user_connected(user: User) -> User:
    if user.is_authenticated:
        logger.info(user)
        logger.info(f"User {user.email} connected.")
        User.objects.filter(id=user.id).update(is_online=True)
        user.is_online = True
        return user
    

@database_sync_to_async
def db_online_users_count():
    counts = User.objects.aggregate(
    regular_users=Count('id', filter=Q(is_online=True, is_staff=False)),
    admin_users=Count('id', filter=Q(is_online=True, is_staff=True))
    )
    data = {
        'regular_users': counts['regular_users'],
        'admin_users': counts['admin_users'],
        'total_users': counts['regular_users']+ counts['admin_users']
    }
    logger.info(data)
    return data
    


@database_sync_to_async
def db_user_disconnected(user: User) -> User:
    user.is_online = False
    user.save()
    return user