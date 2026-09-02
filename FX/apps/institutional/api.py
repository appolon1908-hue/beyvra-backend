from decimal import Decimal
import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.models import OrganizationMembership
from apps.foundation.events import payload_hash
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from .models import (
    AllocationGroup, BrokerAccountMapping, ClearingBroker, ClearingBrokerRelationship,
    CustodyStructure, InstitutionalAccount, InstitutionalSettlementMapping,
    InstitutionalSubaccount, InstitutionalTradeAllocationInstruction, InstitutionalAuditEvent, OmnibusAccount,
    SegregatedCustodyAccount,
)
from .permissions import OPERATOR_ROLES, IsInstitutionalManager, IsInstitutionalOperator
from .serializers import (
    AllocationGroupSerializer, AllocationInstructionSerializer, BrokerAccountMappingSerializer,
    ClearingBrokerSerializer, ClearingRelationshipSerializer, CustodyStructureSafeSerializer,
    InstitutionalAccountSerializer, InstitutionalSubaccountSerializer, OperatorCustodySerializer,
    OperatorOmnibusSerializer, OperatorSegregatedSerializer, SettlementMappingSerializer,
)
from .services import InstitutionAggregationService, InstitutionalAccountReconciler, InstitutionalAccountService, InstitutionalRiskService, SubaccountService


COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", str, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = [*COMMAND_PARAMETERS, OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)]
RECONCILIATION_REQUEST = inline_serializer("InstitutionalReconciliationCommand", {"institution_id": serializers.UUIDField()})
RECONCILIATION_RESPONSE = inline_serializer("InstitutionalReconciliationResult", {
    "id": serializers.UUIDField(), "status": serializers.CharField(), "violations": serializers.ListField(child=serializers.DictField()),
})


def _membership(request):
    return OrganizationMembership.objects.select_related("organization").filter(user=request.user).order_by("organization_id").first()


def _customer_institution(request):
    membership = _membership(request)
    if not membership:
        return None
    return InstitutionalAccount.objects.filter(tenant=membership.organization).order_by("institution_code").first()


def _operator_scope(request, queryset, tenant_path="tenant"):
    """Scope data to every tenant where the caller actually holds an operator role."""
    if request.user.is_superuser:
        return queryset
    return queryset.filter(**{
        f"{tenant_path}__memberships__user": request.user,
        f"{tenant_path}__memberships__role__in": OPERATOR_ROLES,
    })


def _not_configured():
    return Response({"error": {"code": "INSTITUTIONAL_ACCOUNT_NOT_CONFIGURED", "message": "Institutional account access is not configured."}}, status=status.HTTP_404_NOT_FOUND)


def _command_context(request, *, require_version=False):
    key = request.headers.get("Idempotency-Key", "").strip()
    request_id = request.headers.get("X-Request-ID", "").strip()
    expected_version = request.headers.get("If-Match", "").strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128:
        return None, Response({"error": {"code": "VALIDATION_ERROR", "message": "Idempotency-Key and X-Request-ID are required."}}, status=400)
    if require_version and not expected_version:
        return None, Response({"error": {"code": "PRECONDITION_REQUIRED", "message": "If-Match is required."}}, status=428)
    raw_correlation = request.headers.get("X-Correlation-ID") or request_id
    try:
        correlation_id = uuid.UUID(raw_correlation)
    except (TypeError, ValueError):
        return None, Response({"error": {"code": "VALIDATION_ERROR", "message": "X-Request-ID or X-Correlation-ID must provide a UUID correlation identifier."}}, status=400)
    return (key, request_id, correlation_id, expected_version), None


def _version(row):
    return row.updated_at.isoformat().replace("+00:00", "Z")


def _begin_command(request, *, tenant, key, endpoint, payload):
    return begin_idempotent_request(
        key=key, tenant_ref=tenant.pk, actor_ref=request.user.pk, endpoint=endpoint,
        method=request.method, request_data={"api_version": "v1", **payload},
    )


def _replay(record):
    if record.response_status is None or record.response_body is None:
        return Response({"error": {"code": "COMMAND_IN_PROGRESS", "message": "Command result is not yet available."}}, status=409)
    return Response(record.response_body, status=record.response_status)


def _audit_command(*, institution, actor, event_type, object_ref, request_id, correlation_id, before=None, after=None):
    InstitutionalAuditEvent.objects.create(
        institution=institution, actor=actor, event_type=event_type,
        object_type="InstitutionalSubaccount" if "subaccount" in event_type else "InstitutionalReconciliationRun",
        object_ref=str(object_ref), metadata={"request_id": request_id, "correlation_id": str(correlation_id)},
    )
    ApplicationAuditEvent.objects.create(
        actor_ref=str(actor.pk), action=event_type, resource_type="institutional",
        resource_id=str(object_ref), before_hash=payload_hash(before or {}), after_hash=payload_hash(after or {}),
        request_id=request_id, correlation_id=correlation_id, context={"tenant_ref": str(institution.tenant_id)},
        reason="institutional operator command", occurred_at=timezone.now(),
    )


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
    @extend_schema(parameters=COMMAND_PARAMETERS, request=InstitutionalSubaccountSerializer, responses={201: InstitutionalSubaccountSerializer})
    @transaction.atomic
    def post(self, request):
        institution = get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=request.data.get("institution_id"))
        command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        serializer = InstitutionalSubaccountSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        payload = {key: value for key, value in serializer.validated_data.items()}
        payload["institution_id"] = str(institution.pk)
        try:
            record, created = _begin_command(request, tenant=institution.tenant, key=key, endpoint="/api/v1/operator/institutional/subaccounts", payload=payload)
        except IdempotencyConflict:
            return Response({"error": {"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}}, status=409)
        if not created: return _replay(record)
        row = SubaccountService.create(institution=institution, actor=request.user, **serializer.validated_data)
        body = InstitutionalSubaccountSerializer(row).data
        complete_idempotent_request(record, status=201, body=body, resource_type="institutional_subaccount", resource_id=row.pk)
        _audit_command(institution=institution, actor=request.user, event_type="institutional.subaccount.command.created.v1", object_ref=row.pk, request_id=request_id, correlation_id=correlation_id, after=body)
        return Response(body, status=201)


class OperatorSubaccountDetailView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request, subaccount_id): return Response(InstitutionalSubaccountSerializer(get_object_or_404(_operator_scope(request, InstitutionalSubaccount.objects.all()), pk=subaccount_id)).data)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS, request=InstitutionalSubaccountSerializer, responses={200: InstitutionalSubaccountSerializer})
    @transaction.atomic
    def patch(self, request, subaccount_id):
        command, error = _command_context(request, require_version=True)
        if error: return error
        key, request_id, correlation_id, expected_version = command
        row = get_object_or_404(_operator_scope(request, InstitutionalSubaccount.objects.select_for_update()), pk=subaccount_id)
        before = InstitutionalSubaccountSerializer(row).data
        serializer = InstitutionalSubaccountSerializer(row, data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        try:
            record, created = _begin_command(request, tenant=row.tenant, key=key, endpoint=f"/api/v1/operator/institutional/subaccounts/{subaccount_id}", payload={"expected_version": expected_version, **serializer.validated_data})
        except IdempotencyConflict:
            return Response({"error": {"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}}, status=409)
        if not created: return _replay(record)
        if expected_version != _version(row):
            record.delete()
            return Response({"error": {"code": "VERSION_CONFLICT", "message": "Subaccount version does not match."}}, status=409)
        row = serializer.save(); row.full_clean(); row.save()
        body = InstitutionalSubaccountSerializer(row).data
        complete_idempotent_request(record, status=200, body=body, resource_type="institutional_subaccount", resource_id=row.pk)
        _audit_command(institution=row.institution, actor=request.user, event_type="institutional.subaccount.command.updated.v1", object_ref=row.pk, request_id=request_id, correlation_id=correlation_id, before=before, after=body)
        return Response(body)


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
    @extend_schema(parameters=COMMAND_PARAMETERS, request=RECONCILIATION_REQUEST, responses={201: RECONCILIATION_RESPONSE})
    @transaction.atomic
    def post(self, request):
        command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        institution = get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=request.data.get("institution_id"))
        try:
            record, created = _begin_command(request, tenant=institution.tenant, key=key, endpoint="/api/v1/operator/institutional/reconciliation/run", payload={"institution_id": str(institution.pk)})
        except IdempotencyConflict:
            return Response({"error": {"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}}, status=409)
        if not created: return _replay(record)
        run = InstitutionalAccountReconciler.run(institution=institution, actor=request.user)
        body = {"id": str(run.id), "status": run.status, "violations": run.violations}
        complete_idempotent_request(record, status=201, body=body, resource_type="institutional_reconciliation", resource_id=run.pk)
        _audit_command(institution=institution, actor=request.user, event_type="institutional.reconciliation.command.completed.v1", object_ref=run.pk, request_id=request_id, correlation_id=correlation_id, after=body)
        return Response(body, status=201)


class OperatorOwnershipView(APIView):
    permission_classes = [IsInstitutionalOperator]
    def get(self, request, account_id):
        account = get_object_or_404(_operator_scope(request, InstitutionalAccount.objects.all()), pk=account_id)
        return Response({"results": [{"id": str(row.id), "owner_type": row.owner_type, "external_authority": row.external_authority, "external_owner_ref": "***" + row.external_owner_ref[-4:], "ownership_role": row.ownership_role, "status": row.status} for row in account.owner_references.order_by("created_at")]})
