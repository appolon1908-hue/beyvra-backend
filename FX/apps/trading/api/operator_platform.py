from rest_framework import views
from rest_framework.response import Response

from apps.foundation.models import ApplicationAuditEvent, TradingControl
from apps.trading.models import (
    ExecutionProviderHealth,
    ExecutionProviderRecord,
    ExecutionReconciliationRun,
    TradingOrder,
    UnknownExecutionOutcome,
)
from operations.permissions import IsMfaStaff


class OperatorBaseView(views.APIView):
    permission_classes = (IsMfaStaff,)


class OperatorOrderListView(OperatorBaseView):
    def get(self, request):
        rows = TradingOrder.objects.order_by("-created_at")
        state = request.query_params.get("state")
        instrument = request.query_params.get("instrument")
        if state:
            rows = rows.filter(state=state.upper())
        if instrument:
            rows = rows.filter(instrument_id=instrument.upper())
        results = [
            {
                "id": str(row.id),
                "tenant_ref": row.tenant_ref,
                "account_ref": row.account_ref,
                "instrument_id": row.instrument_id,
                "side": row.side,
                "order_type": row.order_type,
                "quantity": str(row.quantity),
                "filled_quantity": str(row.filled_quantity),
                "average_fill_price": str(row.average_fill_price) if row.average_fill_price is not None else None,
                "state": row.state,
                "risk_decision_id": str(row.risk_decision_id) if row.risk_decision_id else None,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
                "simulation": row.simulation,
            }
            for row in rows[:200]
        ]
        return Response({"results": results, "limit": 200})


class OperatorHaltListView(OperatorBaseView):
    def get(self, request):
        rows = TradingControl.objects.order_by("scope", "scope_ref")
        return Response(
            {
                "results": [
                    {
                        "id": row.pk,
                        "scope": row.scope,
                        "scope_ref": row.scope_ref,
                        "state": row.state,
                        "reason": row.reason,
                        "request_id": row.request_id,
                        "changed_by_ref": row.changed_by_ref,
                        "changed_at": row.created_at.isoformat(),
                    }
                    for row in rows
                ]
            }
        )


class OperatorProviderHealthView(OperatorBaseView):
    def get(self, request):
        results = []
        for provider in ExecutionProviderRecord.objects.order_by("priority", "provider_id"):
            health = ExecutionProviderHealth.objects.filter(provider=provider).first()
            results.append(
                {
                    "provider_id": provider.provider_id,
                    "display_name": provider.display_name,
                    "mode": provider.mode,
                    "enabled": provider.enabled,
                    "governance_state": provider.governance_state,
                    "state": health.state if health else "UNKNOWN",
                    "circuit_state": health.circuit_state if health else "UNKNOWN",
                    "connection_state": health.connection_state if health else "UNKNOWN",
                    "latency_p95_ms": health.latency_p95_ms if health else None,
                    "error_rate": str(health.error_rate) if health else None,
                    "last_checked_at": health.last_checked_at.isoformat() if health else None,
                    "live_routing_enabled": bool(provider.enabled and provider.mode == "LIVE"),
                }
            )
        return Response({"results": results})


class OperatorReconciliationBreaksView(OperatorBaseView):
    def get(self, request):
        outcomes = UnknownExecutionOutcome.objects.filter(state="UNRESOLVED").select_related("execution")[:200]
        latest_run = ExecutionReconciliationRun.objects.order_by("-completed_at").first()
        return Response(
            {
                "latest_run": {
                    "id": str(latest_run.id),
                    "status": latest_run.status,
                    "candidate_sha": latest_run.candidate_sha,
                    "warning_count": latest_run.warning_count,
                    "critical_count": latest_run.critical_count,
                    "completed_at": latest_run.completed_at.isoformat(),
                }
                if latest_run
                else None,
                "results": [
                    {
                        "id": str(row.id),
                        "execution_id": str(row.execution_id),
                        "classification": row.classification,
                        "state": row.state,
                        "lookup_attempts": row.lookup_attempts,
                        "last_lookup_at": row.last_lookup_at.isoformat() if row.last_lookup_at else None,
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in outcomes
                ],
                "resolution_mutation_enabled": False,
                "resolution_requirement": "INDEPENDENT_EVIDENCE_AND_MAKER_CHECKER_APPROVAL",
            }
        )


class OperatorAuditEventView(OperatorBaseView):
    def get(self, request):
        rows = ApplicationAuditEvent.objects.order_by("-occurred_at")
        resource_type = request.query_params.get("resource_type")
        action = request.query_params.get("action")
        if resource_type:
            rows = rows.filter(resource_type=resource_type)
        if action:
            rows = rows.filter(action=action)
        return Response(
            {
                "results": [
                    {
                        "event_id": str(row.event_id),
                        "actor_ref": row.actor_ref,
                        "action": row.action,
                        "resource_type": row.resource_type,
                        "resource_id": row.resource_id,
                        "request_id": row.request_id,
                        "correlation_id": str(row.correlation_id),
                        "reason": row.reason,
                        "occurred_at": row.occurred_at.isoformat(),
                    }
                    for row in rows[:500]
                ],
                "limit": 500,
            }
        )
