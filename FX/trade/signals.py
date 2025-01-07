import channels.layers
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver
from fx_utils.constants import DATE_FORMAT
from ws.constants import TRADE_GROUP

from .models import Trade
from .serializers import TradeSerializer


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
