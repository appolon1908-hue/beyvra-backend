from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework import serializers
from trade.models import Trade
from trade.serializers import TradeSerializer
from django.contrib.auth.models import User
from .service import UserNotificationService


        

        

