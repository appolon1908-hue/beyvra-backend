from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework import serializers
from trade.models import Trade
from trade.serializers import TradeSerializer
from django.contrib.auth.models import User
from .service import UserNotificationService



@receiver(post_save, sender=Trade)
def send_trade_updates(sender, instance, created, **kwargs):
    if created:
        print(instance)
        # subject = "New User Registration"
        # message = f"A new user has registered with the username: {instance.username}"
        

        

