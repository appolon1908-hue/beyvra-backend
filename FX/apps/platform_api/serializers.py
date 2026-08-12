from rest_framework import serializers


class SafeErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(required=False)


class SafeErrorSerializer(serializers.Serializer):
    error = SafeErrorDetailSerializer()


class ListEnvelopeSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    next = serializers.CharField(allow_null=True, required=False)


class MeSerializer(serializers.Serializer):
    id = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    display_name = serializers.CharField(allow_blank=True)
    tenant_id = serializers.UUIDField(allow_null=True)
    mfa_enabled = serializers.BooleanField()


class SupportMessageSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    body = serializers.CharField(max_length=4000)
    created_at = serializers.DateTimeField(read_only=True)


class SupportCaseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    subject = serializers.CharField(max_length=160)
    message = serializers.CharField(max_length=4000, write_only=True, required=False)
    status = serializers.CharField(read_only=True)
    messages = SupportMessageSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class SupportCasePageSerializer(serializers.Serializer):
    results = SupportCaseSerializer(many=True)
    next = serializers.CharField(allow_null=True)


class ReportExportSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    type = serializers.ChoiceField(choices=("activity", "trades", "fees", "transactions", "statements"))
    status = serializers.CharField(read_only=True)
    filters = serializers.DictField(write_only=True, required=False)
    created_at = serializers.DateTimeField(read_only=True)


class PrivacyRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    type = serializers.ChoiceField(choices=("EXPORT", "DELETION"), read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class PrivacyRequestPageSerializer(serializers.Serializer):
    results = PrivacyRequestSerializer(many=True)
    next = serializers.CharField(allow_null=True)


class OperatorActionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    action_type = serializers.CharField(max_length=64)
    target_ref = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=500, write_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class OperatorActionPageSerializer(serializers.Serializer):
    results = OperatorActionSerializer(many=True)
    next = serializers.CharField(allow_null=True)


class WebhookEventSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=120)
    data = serializers.DictField(required=False)


class WebhookAckSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("accepted", "duplicate", "ignored"))


class StatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    server_time = serializers.DateTimeField()
    api_version = serializers.CharField()


class FeatureSerializer(serializers.Serializer):
    features = serializers.DictField(child=serializers.BooleanField())


class DisabledFeatureSerializer(SafeErrorSerializer):
    pass
