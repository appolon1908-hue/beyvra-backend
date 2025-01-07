import os
import channels.layers
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver
from ws.constants import WALLET_GROUP

from .models import Wallet, ManualBalanceUpdate
from .serializers import WalletCreateSerializer
from .tasks import async_send_balance_update_email


@receiver(post_save, sender=Wallet)
def update_with_ws(sender, instance, **kwargs):
    """
    Sends update/create updates to the user with channel
    """
    channel_layer = channels.layers.get_channel_layer()
    obj = WalletCreateSerializer(instance)
    user = instance.user
    if user.is_online:
        async_to_sync(channel_layer.group_send)(
            f"{user.id}",
            {"type": "send_message", "a": "u", "m": WALLET_GROUP, "d": [obj.data]},
        )


@receiver(post_save, sender=ManualBalanceUpdate, dispatch_uid="notify_balance_update")
def notify_balance_update(sender, instance, **kwargs):
    """ On manual balance create/update, send an email to the user """
    async_send_balance_update_email.delay(instance.id)
