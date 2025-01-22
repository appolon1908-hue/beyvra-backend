from channels.db import database_sync_to_async
from users.models import User
from django.db.models import Count, Q
from django.core.cache import cache
import uuid


#1:f06e75bc-55ef-4eeb-a559-4d0fa0df2ace
#2:6ae71e8b-41f3-4a89-bc05-02c0ea57d3ed



@database_sync_to_async
def can_access_group(self):
    """Check if user can access the requested group"""
    if self.user.is_staff:
        return self.group_name in self.GROUPS['admin']
    return self.group_name in self.GROUPS['user']

@database_sync_to_async
def db_user_connected(user: User) -> User:
    if user.is_authenticated:
        User.objects.filter(id=user.id).update(is_online=True)
        user.is_online = True  # Update instance to maintain consistency
        return user


@database_sync_to_async
def db_online_users_count():
    ##Added cache to optimize database
    cache_key = 'online_users_count'
    cached_result = cache.get(cache_key)
    print(cached_result)
    if cached_result is None:
        counts = User.objects.aggregate(
        regular_users=Count('id', filter=Q(is_online=True, is_staff=False)),
        admin_users=Count('id', filter=Q(is_online=True, is_staff=True))
        )
    return {
        'regular_users': counts['regular_users'],
        'admin_users': counts['admin_users'],
        'total_users': counts['regular_users']+ counts['admin_users']
    }


@database_sync_to_async
def db_user_disconnected(user: User) -> User:
    user.is_online = False
    user.save()
    return user