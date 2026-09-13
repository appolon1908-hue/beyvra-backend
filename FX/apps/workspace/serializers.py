from rest_framework import serializers
from apps.trading.api.serializers import TradingAccountSerializer

from .instruments import InstrumentResolutionError, resolve_active_instrument
from .models import Watchlist, WatchlistItem


class WorkspaceAccountSerializer(TradingAccountSerializer):
    id = serializers.UUIDField(read_only=True)


class WorkspaceBootstrapSerializer(serializers.Serializer):
    state = serializers.CharField(read_only=True)
    tenant = serializers.DictField(read_only=True)
    account = WorkspaceAccountSerializer(read_only=True)
    realtime = serializers.DictField(read_only=True)
    wallet = serializers.DictField(read_only=True)
    notifications = serializers.DictField(read_only=True)
    features = serializers.DictField(child=serializers.BooleanField(), read_only=True)
    instrument = serializers.DictField(read_only=True)
    instruments = serializers.ListField(child=serializers.CharField(), read_only=True)
    tradingRules = serializers.DictField(read_only=True)
    savedAssetTabs = serializers.ListField(child=serializers.CharField(), read_only=True)
    chartPreferences = serializers.DictField(read_only=True)


class WatchlistItemSerializer(serializers.ModelSerializer):
    instrument_id = serializers.CharField(max_length=64)
    symbol = serializers.SerializerMethodField()

    class Meta:
        model = WatchlistItem
        fields = ("id", "instrument_id", "symbol", "sort_order", "created_at")
        read_only_fields = ("id", "symbol", "created_at")

    def validate_instrument_id(self, value):
        resolved = self.context.get("resolved_instrument")
        if resolved is not None:
            return str(resolved.instrument_id)
        try:
            instrument = resolve_active_instrument(value)
        except InstrumentResolutionError as exc:
            raise serializers.ValidationError(exc.code) from exc
        return str(instrument.instrument_id)

    def get_symbol(self, obj):
        try:
            return resolve_active_instrument(obj.instrument_id).canonical_symbol
        except InstrumentResolutionError:
            return None


class WatchlistSerializer(serializers.ModelSerializer):
    items = WatchlistItemSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields = (
            "id",
            "name",
            "is_default",
            "version",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_default",
            "version",
            "items",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        normalized = " ".join(value.split())
        if not normalized:
            raise serializers.ValidationError("Name is required.")
        return normalized
