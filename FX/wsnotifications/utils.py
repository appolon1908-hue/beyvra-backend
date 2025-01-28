from channels.db import database_sync_to_async
from users.models import User
from django.db.models import Count, Q
from django.core.cache import cache
import uuid
from users.models import UserDeviceInfo
from wsnotifications.models import AssetSubscription


import logging

logger = logging.getLogger(__name__)






@database_sync_to_async
def subscribe_to_asset(user, asset_id):
    AssetSubscription.objects.get_or_create(
        user= user,
        asset_id=asset_id
    )
    return asset_id
    
@database_sync_to_async
def unsubscribe_from_asset(user, asset_id):
    AssetSubscription.objects.filter(
        user= user,
        asset_id=asset_id
    ).delete()
    return asset_id

@database_sync_to_async
def db_user_connected(user: User) -> User:
    if user.is_authenticated:
        User.objects.filter(id=user.id).update(is_online=True)
        user.is_online = True  # Update instance to maintain consistency
        return user


@database_sync_to_async
def db_online_users_count():
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