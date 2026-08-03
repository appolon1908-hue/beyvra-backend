import ipaddress
import socket
from urllib.parse import urlparse
from rest_framework import serializers

from users.models import User
from .models import CRMConnection, DemoAccount, DemoLedgerEntry, UserImport, UserImportRow


class UserCreateSerializer(serializers.Serializer):
    external_user_id = serializers.CharField(max_length=255)
    first_name = serializers.CharField(max_length=20)
    last_name = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=16)
    organization_id = serializers.UUIDField()
    locale = serializers.CharField(max_length=10, required=False, default="en")
    country = serializers.CharField(max_length=5, required=False, default="US")
    source = serializers.CharField(max_length=80, required=False, default="third_party_crm")
    consent = serializers.DictField(required=False, default=dict)
    metadata = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        consent = attrs["consent"]
        if consent.get("terms_accepted") is not True:
            raise serializers.ValidationError({"consent": "terms_accepted must be true"})
        return attrs


class DemoAccountSerializer(serializers.ModelSerializer):
    virtual_balance = serializers.SerializerMethodField()
    class Meta:
        model = DemoAccount
        fields = ("id", "account_type", "currency", "virtual_balance", "withdrawable", "transferable", "real_money")
    def get_virtual_balance(self, obj):
        return "2000.00"


class CRMConnectionSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = CRMConnection
        fields = ("id", "name", "provider", "endpoint", "secret", "field_mapping", "event_categories", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_endpoint(self, value):
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise serializers.ValidationError("CRM endpoints must use HTTPS")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
            if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback or ipaddress.ip_address(address).is_link_local for address in addresses):
                raise serializers.ValidationError("private and metadata destinations are not allowed")
        except socket.gaierror:
            raise serializers.ValidationError("endpoint hostname could not be resolved")
        return value


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserImportRow
        fields = ("row_number", "data", "errors", "status", "user")


class ImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserImport
        fields = ("id", "status", "file_name", "row_count", "valid_count", "invalid_count", "created_at", "updated_at")
