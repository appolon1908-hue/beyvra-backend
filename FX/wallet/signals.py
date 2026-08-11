import os
import channels.layers
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from ws.constants import WALLET_GROUP

from .models import Wallet, ManualBalanceUpdate, Transaction
from notifications.services import emit_notification
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
    emit_notification(
        user_id=instance.wallet.user_id,
        title="Account balance updated",
        message="An administrator updated your account balance.",
        category="ACCOUNT_CHANGE",
        payload={"wallet_id": instance.wallet_id, "update_id": str(instance.id)},
    )


@receiver(pre_save, sender=Transaction, dispatch_uid="capture_transaction_previous_status")
def capture_transaction_previous_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender=Transaction, dispatch_uid="persist_transaction_notification")
def persist_transaction_notification(sender, instance, created, **kwargs):
    if not created and getattr(instance, "_previous_status", None) == instance.status:
        return
    transaction_type = {"D": "deposit", "W": "withdrawal", "TD": "trade", "TN": "transfer"}.get(
        instance.type, "transaction"
    )
    state = {"P": "pending", "S": "completed", "F": "failed", "R": "rejected"}.get(
        instance.status, "updated"
    )
    emit_notification(
        user_id=instance.wallet.user_id,
        title=f"{transaction_type.title()} {state}",
        message=f"Your {transaction_type} is {state}.",
        category=transaction_type,
        payload={
            "transaction_id": str(instance.transaction_id),
            "wallet_id": instance.wallet_id,
            "status": instance.status,
            "amount": str(instance.amount),
        },
    )
