from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.models import OrganizationMembership
from .models import (
    AllocationGroup, BrokerAccountMapping, ClearingBroker, ClearingBrokerRelationship,
    CustodyStructure, InstitutionalAccount, InstitutionalSettlementMapping,
    InstitutionalSubaccount, InstitutionalTradeAllocationInstruction, OmnibusAccount,
    SegregatedCustodyAccount,
)
from .permissions import IsInstitutionalManager, IsInstitutionalOperator
from .serializers import (
    AllocationGroupSerializer, AllocationInstructionSerializer, BrokerAccountMappingSerializer,
    ClearingBrokerSerializer, ClearingRelationshipSerializer, CustodyStructureSafeSerializer,
    InstitutionalAccountSerializer, InstitutionalSubaccountSerializer, OperatorCustodySerializer,
    OperatorOmnibusSerializer, OperatorSegregatedSerializer, SettlementMappingSerializer,
)
from .services import InstitutionAggregationService, InstitutionalAccountReconciler, InstitutionalAccountService, InstitutionalRiskService, SubaccountService


def _membership(request):
    return OrganizationMembership.objects.select_related("organization").filter(user=request.user).order_by("organization_id").first()


def _customer_institution(request):
    membership = _membership(request)
    if not membership:
        return None
    return InstitutionalAccount.objects.filter(tenant=membership.organization).order_by("institution_code").first()


def _operator_tenant(request):
    membership = _membership(request)
    return membership.organization if membership else None


def _operator_scope(request, queryset, tenant_path="tenant"):
    """Keep operator access tenant-bound; global reference data opts out explicitly."""
    if request.user.is_superuser:
        return queryset
    tenant = _operator_tenant(request)
    if tenant is None:
        return queryset.none()
    return queryset.filter(**{tenant_path: tenant})


def _not_configured():
    return Response({"error": {"code": "INSTITUTIONAL_ACCOUNT_NOT_CONFIGURED", "message": "Institutional account access is not configured."}}, status=status.HTTP_404_NOT_FOUND)


class AccountView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response(InstitutionalAccountSerializer(institution).data) if institution else _not_configured()


class HierarchyView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response({"institution": InstitutionalAccountSerializer(institution).data, "subaccounts": InstitutionalAccountService.get_hierarchy(account=institution)}) if institution else _not_configured()


class SubaccountListView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        return Response({"results": InstitutionalSubaccountSerializer(institution.subaccounts.order_by("code", "id"), many=True).data})


class SubaccountDetailView(APIView):
    def get(self, request, subaccount_id):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        row = get_object_or_404(InstitutionalSubaccount, pk=subaccount_id, institution=institution)
        return Response(InstitutionalSubaccountSerializer(row).data)


class SubaccountResourceView(APIView):
    resource = "positions"
    def get(self, request, subaccount_id):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        row = get_object_or_404(InstitutionalSubaccount, pk=subaccount_id, institution=institution)
        if self.resource == "positions":
            results = [{"instrument_id": item.instrument_id, "quantity": str(item.quantity), "as_of": item.as_of, "simulation": item.simulation} for item in row.positions.order_by("instrument_id")]
        elif self.resource == "risk":
            return Response(InstitutionalRiskService.evaluate(institution=institution, subaccount=row))
        else:
            results = []
        return Response({"results": results})


class PositionsView(SubaccountResourceView): resource = "positions"
class OrdersView(SubaccountResourceView): resource = "orders"
class TradesView(SubaccountResourceView): resource = "trades"
class SubaccountRiskView(SubaccountResourceView): resource = "risk"


class PortfolioView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        return Response({"institution_id": str(institution.id), "positions": InstitutionAggregationService.positions(institution=institution), "cash": InstitutionAggregationService.cash_view(institution=institution), "simulation": True})


class InstitutionPositionsView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response({"results": InstitutionAggregationService.positions(institution=institution)}) if institution else _not_configured()


class ExposureView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response(InstitutionAggregationService.exposure(institution=institution)) if institution else _not_configured()


class RiskView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response(InstitutionalRiskService.evaluate(institution=institution)) if institution else _not_configured()


class EmptyInstitutionResourceView(APIView):
    def get(self, request):
        return Response({"results": []}) if _customer_institution(request) else _not_configured()


class AllocationGroupListView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response({"results": AllocationGroupSerializer(institution.allocation_groups.order_by("code"), many=True).data}) if institution else _not_configured()


class AllocationGroupDetailView(APIView):
    def get(self, request, group_id):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        return Response(AllocationGroupSerializer(get_object_or_404(AllocationGroup, pk=group_id, institution=institution)).data)


class AllocationListView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        return Response({"results": AllocationInstructionSerializer(institution.trade_allocations.prefetch_related("lines"), many=True).data}) if institution else _not_configured()


class AllocationDetailView(APIView):
    def get(self, request, allocation_id):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        return Response(AllocationInstructionSerializer(get_object_or_404(InstitutionalTradeAllocationInstruction.objects.prefetch_related("lines"), pk=allocation_id, institution=institution)).data)


class CustodyStructureView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        row = institution.custody_structures.order_by("-effective_from").first()
        return Response(CustodyStructureSafeSerializer(row).data) if row else Response({"error": {"code": "CUSTODY_CONFIGURATION_UNAVAILABLE", "message": "Custody configuration is unavailable."}}, status=404)


class ReconciliationStatusView(APIView):
    def get(self, request):
        institution = _customer_institution(request)
        if not institution: return _not_configured()
        run = institution.reconciliation_runs.order_by("-started_at").first()
        return Response({"status": run.status if run else "NOT_RUN", "violation_count": len(run.violations) if run else 0, "last_run_at": run.completed_at if run else None})


class OperatorAccountsView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request): return Response({"results": InstitutionalAccountSerializer(_operator_scope(request, InstitutionalAccount.objects.all()).order_by("institution_code"), many=True).data})


class OperatorAccountDetailView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request, account_id): return Response(InstitutionalAccountSerializer(get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=account_id)).data)


class OperatorSubaccountsView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request): return Response({"results": InstitutionalSubaccountSerializer(_operator_scope(request, InstitutionalSubaccount.objects.all()).order_by("code"), many=True).data})
    def post(self, request):
        membership = _membership(request); institution = get_object_or_404(InstitutionalAccount, pk=request.data.get("institution_id"), tenant=membership.organization)
        serializer = InstitutionalSubaccountSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        row = SubaccountService.create(institution=institution, actor=request.user, **serializer.validated_data)
        return Response(InstitutionalSubaccountSerializer(row).data, status=201)


class OperatorSubaccountDetailView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request, subaccount_id): return Response(InstitutionalSubaccountSerializer(get_object_or_404(_operator_scope(request, InstitutionalSubaccount.objects.all()), pk=subaccount_id)).data)
    def patch(self, request, subaccount_id):
        row = get_object_or_404(_operator_scope(request, InstitutionalSubaccount.objects.all()), pk=subaccount_id)
        serializer = InstitutionalSubaccountSerializer(row, data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        row = serializer.save(); row.full_clean(); row.save()
        return Response(InstitutionalSubaccountSerializer(row).data)


class OperatorCollectionView(APIView):
    permission_classes = [IsInstitutionalOperator]
    model = InstitutionalAccount; serializer_class = InstitutionalAccountSerializer
    tenant_path = "institution__tenant"
    def get(self, request):
        queryset = self.model.objects.all()
        if self.tenant_path:
            queryset = _operator_scope(request, queryset, self.tenant_path)
        return Response({"results": self.serializer_class(queryset.order_by("id"), many=True).data})


class OperatorCustodyView(OperatorCollectionView): model = CustodyStructure; serializer_class = OperatorCustodySerializer
class OperatorOmnibusView(OperatorCollectionView): model = OmnibusAccount; serializer_class = OperatorOmnibusSerializer
class OperatorSegregatedView(OperatorCollectionView): model = SegregatedCustodyAccount; serializer_class = OperatorSegregatedSerializer
class OperatorAllocationGroupsView(OperatorCollectionView): model = AllocationGroup; serializer_class = AllocationGroupSerializer
class OperatorAllocationsView(OperatorCollectionView): model = InstitutionalTradeAllocationInstruction; serializer_class = AllocationInstructionSerializer
class OperatorClearingBrokersView(OperatorCollectionView): model = ClearingBroker; serializer_class = ClearingBrokerSerializer; tenant_path = None
class OperatorClearingRelationshipsView(OperatorCollectionView): model = ClearingBrokerRelationship; serializer_class = ClearingRelationshipSerializer
class OperatorBrokerMappingsView(OperatorCollectionView): model = BrokerAccountMapping; serializer_class = BrokerAccountMappingSerializer
class OperatorSettlementMappingsView(OperatorCollectionView): model = InstitutionalSettlementMapping; serializer_class = SettlementMappingSerializer


class OperatorReconciliationView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request):
        queryset = __import__("apps.institutional.models", fromlist=["InstitutionalReconciliationRun"]).InstitutionalReconciliationRun.objects.all()
        queryset = _operator_scope(request, queryset, "institution__tenant").order_by("-started_at")
        results = [{"id": str(run.id), "institution_id": str(run.institution_id), "status": run.status, "violation_count": len(run.violations), "completed_at": run.completed_at} for run in queryset]
        return Response({"results": results})
    def post(self, request):
        institution = get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=request.data.get("institution_id"))
        run = InstitutionalAccountReconciler.run(institution=institution, actor=request.user)
        return Response({"id": str(run.id), "status": run.status, "violations": run.violations}, status=201)


class OperatorOwnershipView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request, account_id):
        account = get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=account_id)
        return Response({"results": [{"id": str(row.id), "owner_type": row.owner_type, "external_authority": row.external_authority, "external_owner_ref": "***" + row.external_owner_ref[-4:], "ownership_role": row.ownership_role, "status": row.status} for row in account.owner_references.order_by("created_at")]})
