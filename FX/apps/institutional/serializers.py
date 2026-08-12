from rest_framework import serializers

from .models import (
    AllocationGroup, AllocationGroupMember, BrokerAccountMapping, ClearingBroker,
    ClearingBrokerRelationship, CustodyStructure, InstitutionalAccount,
    InstitutionalSettlementMapping, InstitutionalSubaccount,
    InstitutionalTradeAllocationInstruction, OmnibusAccount, SegregatedCustodyAccount,
)


class InstitutionalAccountSerializer(serializers.ModelSerializer):
    tenant_id = serializers.UUIDField(read_only=True)
    class Meta:
        model = InstitutionalAccount
        fields = ("id", "tenant_id", "institution_code", "display_name", "account_type", "status", "base_currency", "effective_from", "effective_to", "created_at", "updated_at")
        read_only_fields = ("id", "tenant_id", "created_at", "updated_at")


class InstitutionalSubaccountSerializer(serializers.ModelSerializer):
    institution_id = serializers.UUIDField(read_only=True)
    tenant_id = serializers.UUIDField(read_only=True)
    class Meta:
        model = InstitutionalSubaccount
        fields = ("id", "institution_id", "tenant_id", "parent_subaccount_id", "code", "display_name", "subaccount_type", "base_currency", "status", "risk_profile_ref", "trading_policy_ref", "allocation_eligible", "effective_from", "effective_to", "created_at", "updated_at")
        read_only_fields = ("id", "institution_id", "tenant_id", "created_at", "updated_at")


class CustodyStructureSafeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustodyStructure
        fields = ("id", "custody_model", "status", "policy_version", "effective_from", "effective_to")


class AllocationGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllocationGroup
        fields = ("id", "institution_id", "code", "name", "allocation_method", "status", "effective_from", "effective_to")
        read_only_fields = ("id", "institution_id")


class AllocationGroupMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllocationGroupMember
        fields = ("id", "allocation_group_id", "subaccount_id", "weight", "fixed_quantity", "priority", "status", "effective_from", "effective_to")
        read_only_fields = ("id", "allocation_group_id")


class AllocationInstructionSerializer(serializers.ModelSerializer):
    lines = serializers.SerializerMethodField()
    class Meta:
        model = InstitutionalTradeAllocationInstruction
        fields = ("id", "trade_id", "allocation_group_id", "source_account_id", "allocation_method", "state", "policy_version", "canonical_quantity", "created_at", "updated_at", "lines")
    def get_lines(self, obj):
        return [{"target_subaccount_id": str(line.target_subaccount_id), "quantity": str(line.quantity), "notional": str(line.notional), "fee_share": str(line.fee_share) if line.fee_share is not None else None, "status": line.status} for line in obj.lines.all()]


class OperatorCustodySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustodyStructure
        fields = "__all__"


class OperatorOmnibusSerializer(serializers.ModelSerializer):
    external_account_ref = serializers.SerializerMethodField()
    class Meta:
        model = OmnibusAccount
        fields = ("id", "institution_id", "custody_structure_id", "provider_id", "external_account_ref", "asset_class", "currency", "status", "environment", "created_at", "updated_at")
    def get_external_account_ref(self, obj): return "***" + obj.external_account_ref[-4:] if obj.external_account_ref else ""


class OperatorSegregatedSerializer(serializers.ModelSerializer):
    external_account_ref = serializers.SerializerMethodField()
    class Meta:
        model = SegregatedCustodyAccount
        fields = ("id", "institution_id", "subaccount_id", "provider_id", "external_account_ref", "custody_structure_id", "status", "environment", "effective_from", "effective_to")
    def get_external_account_ref(self, obj): return "***" + obj.external_account_ref[-4:] if obj.external_account_ref else ""


class ClearingBrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClearingBroker
        fields = ("id", "code", "name", "status", "environment", "supported_asset_classes", "created_at", "updated_at")


class ClearingRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClearingBrokerRelationship
        exclude = ("approved_for_live",)


class BrokerAccountMappingSerializer(serializers.ModelSerializer):
    provider_account_ref = serializers.SerializerMethodField()
    class Meta:
        model = BrokerAccountMapping
        fields = ("id", "institution_id", "subaccount_id", "execution_provider_id", "clearing_broker_id", "provider_account_ref", "account_role", "environment", "status", "effective_from", "effective_to")
    def get_provider_account_ref(self, obj): return "***" + obj.provider_account_ref[-4:]


class SettlementMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstitutionalSettlementMapping
        fields = "__all__"
