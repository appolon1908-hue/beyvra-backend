from django.contrib.auth import get_user_model
from rest_framework import serializers
from tickets.models import SupportTicket


class GetTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False, allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "first_name", "last_name")


class TicketSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    assigned_admin = UserSerializer()

    class Meta:
        model = SupportTicket
        fields = ("id", "user", "subject", "message", "status", "created_at", "updated_at", "assigned_admin")
