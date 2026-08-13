from rest_framework import serializers
from .domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState


class RestrictionSummarySerializer(serializers.Serializer):
    restriction_id = serializers.UUIDField()
    type = serializers.CharField()
    reason_code = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)


class ComplianceProfileResponseSerializer(serializers.Serializer):
    kyc_state = serializers.ChoiceField(choices=[x.value for x in KycState])
    aml_state = serializers.ChoiceField(choices=[x.value for x in AmlState])
    sanctions_state = serializers.ChoiceField(choices=[x.value for x in SanctionsState])
    jurisdiction_state = serializers.ChoiceField(choices=[x.value for x in JurisdictionState])
    account_state = serializers.ChoiceField(choices=[x.value for x in AccountState])
    restrictions = RestrictionSummarySerializer(many=True)
    requirements = serializers.ListField(child=serializers.CharField())
    last_updated = serializers.DateTimeField()


class ComplianceRequirementSerializer(serializers.Serializer):
    requirement_id = serializers.UUIDField()
    type = serializers.CharField()
    status = serializers.CharField()
    required = serializers.BooleanField()
    deadline = serializers.DateTimeField(allow_null=True)
    user_action = serializers.CharField(allow_blank=True)


class ComplianceRequirementsResponseSerializer(serializers.Serializer):
    results = ComplianceRequirementSerializer(many=True)


class SafeComplianceErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class SafeComplianceErrorEnvelopeSerializer(serializers.Serializer):
    error = SafeComplianceErrorSerializer()
