import ipaddress
import socket
from urllib.parse import urlparse
from rest_framework import serializers

from users.models import User
from .models import CRMConnection, DemoAccount, DemoLedgerEntry, ServiceToken, UserImport, UserImportRow


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
    secret = serializers.CharField(write_only=True, required=True, min_length=16)
    class Meta:
        model = CRMConnection
        fields = ("id", "name", "provider", "endpoint", "secret", "field_mapping", "event_categories", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_endpoint(self, value):
        try:
            parsed = urlparse(value)
            port = parsed.port
            if (parsed.scheme != "https" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.fragment or "%" in parsed.hostname
                    or any(ord(char) <= 32 for char in value)):
                raise ValueError("invalid HTTPS authority")
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port or 443, type=socket.SOCK_STREAM)}
            if not addresses:
                raise ValueError("empty DNS answer")
            for address in addresses:
                ip = ipaddress.ip_address(address)
                if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                    ip = ip.ipv4_mapped
                if not ip.is_global or ip.is_multicast or ip.is_reserved:
                    raise ValueError("nonpublic destination")
        except (ValueError, socket.gaierror) as exc:
            raise serializers.ValidationError("CRM endpoint must resolve to public HTTPS destinations") from exc
        return value


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserImportRow
        fields = ("row_number", "data", "errors", "status", "user")


class ImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserImport
        fields = ("id", "status", "file_name", "row_count", "valid_count", "invalid_count", "created_at", "updated_at")


class ServiceTokenMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceToken
        fields = ("id", "name", "scopes", "environment", "fingerprint", "last_four", "expires_at", "last_used_at", "revoked_at", "created_at")
        read_only_fields = fields


class ServiceTokenIssueSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, default="integration")
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=(
            "users:read", "users:write", "users:import", "demo_accounts:read",
            "crm_connections:read", "crm_connections:write", "crm_deliveries:read",
            "crm_deliveries:retry", "webhooks:read", "webhooks:write",
        )), default=list, max_length=10,
    )

    def validate_scopes(self, value):
        return sorted(set(value))


class ServiceTokenActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("revoke", "rotate"), default="revoke")
