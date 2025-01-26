from django.contrib.auth import get_user_model
from rest_framework import serializers
from tickets.models import SupportTicket


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "first_name", "last_name")


class TicketSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    assigned_admin = UserSerializer()

    class Meta:
        model = SupportTicket
        fields = "__all__"
