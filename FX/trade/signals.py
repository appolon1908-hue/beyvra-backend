import channels.layers
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from fx_utils.constants import DATE_FORMAT
from ws.constants import TRADE_GROUP

from .models import Trade
from .serializers import TradeSerializer
from notifications.services import emit_notification


@receiver(pre_save, sender=Trade, dispatch_uid="capture_trade_previous_state")
def capture_trade_previous_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._was_active = None
        return
    instance._was_active = sender.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()


@receiver(post_save, sender=Trade)
def update_with_ws(sender, instance, created, **kwargs):
    """
    Sends update/create updates to the user with channel
    """
    channel_layer = channels.layers.get_channel_layer()
    obj = TradeSerializer(instance)
    data = obj.data
    data["created_at"] = instance.created_at.strftime(DATE_FORMAT)
    data["updated_at"] = instance.updated_at.strftime(DATE_FORMAT)
    if instance.result_time is not None:
        data["result_time"] = instance.result_time.strftime(DATE_FORMAT)
    user = instance.wallet.user
    action = "c" if created else "u"
    if user.is_online:
        async_to_sync(channel_layer.group_send)(
            f"{user.id}",
            {"type": "send_message", "a": action, "m": TRADE_GROUP, "d": [data]},
        )
    if created:
        emit_notification(
            user_id=user.id,
            title="Trade order placed",
            message=f"Your {instance.asset.symbol} trade order was placed.",
            category="TRADE",
            payload={"trade_id": instance.id, "status": "open", "symbol": instance.asset.symbol},
        )
    elif getattr(instance, "_was_active", None) is True and not instance.is_active:
        rejected = instance.transaction.status == "R"
        emit_notification(
            user_id=user.id,
            title="Trade rejected" if rejected else "Trade completed",
            message=(f"Your {instance.asset.symbol} trade was cancelled."
                     if rejected else f"Your {instance.asset.symbol} trade completed."),
            category="TRADE",
            payload={"trade_id": instance.id, "status": "rejected" if rejected else "completed",
                     "symbol": instance.asset.symbol, "net": str(instance.net)},
        )
