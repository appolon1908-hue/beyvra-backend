from rest_framework import serializers

from .models import (
    AccountDeletionRequest,
    FraudCase,
    Notification,
    NotificationPreference,
    PrivacyExportJob,
    ReportJob,
    Statement,
    SupportCase,
    SupportCaseEvent,
    TransactionHistoryEntry,
)


class FraudCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FraudCase
        exclude = ("tenant_id",)
        read_only_fields = (
            "case_id",
            "created_at",
            "updated_at",
            "resolved_at",
            "resolution",
        )


class SupportCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportCase
        fields = (
            "case_id",
            "category",
            "priority",
            "status",
            "created_at",
            "updated_at",
            "resolved_at",
            "safe_summary",
        )
        read_only_fields = (
            "case_id",
            "status",
            "created_at",
            "updated_at",
            "resolved_at",
        )


class CustomerSupportEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportCaseEvent
        fields = ("event_id", "event_type", "body_safe", "created_at")
        read_only_fields = fields


class SupportMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=5000, trim_whitespace=True)


class TransactionSerializer(serializers.ModelSerializer):
    amount = serializers.CharField()
    fee = serializers.CharField()

    class Meta:
        model = TransactionHistoryEntry
        exclude = ("tenant_id", "account")


class TransactionQuerySerializer(serializers.Serializer):
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError(
                    {"date_to": "The end of the range must not precede the start."}
                )
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        exclude = ("tenant_id", "account", "failure_reason_safe", "attempts")


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ("category", "channel", "enabled", "updated_at")
        read_only_fields = ("updated_at",)


class ReportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportJob
        exclude = ("tenant_id", "account", "artifact_ref")
        read_only_fields = (
            "job_id",
            "parameters_hash",
            "status",
            "created_at",
            "completed_at",
            "expires_at",
            "reconciliation_passed",
        )


class StatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        exclude = ("tenant_id", "account")


class PrivacyExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacyExportJob
        exclude = ("tenant_id", "account", "artifact_ref")
        read_only_fields = (
            "job_id",
            "status",
            "created_at",
            "completed_at",
            "expires_at",
            "policy_version",
        )


class AccountDeletionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountDeletionRequest
        exclude = ("tenant_id", "account")
        read_only_fields = (
            "request_id",
            "status",
            "requested_at",
            "reviewed_at",
            "completed_at",
            "policy_version",
            "retained_categories",
            "anonymized_categories",
            "blocked_by_legal_hold",
        )
