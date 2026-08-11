import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.foundation.models import ApplicationAuditEvent, TradingControl
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from .errors import error_response


class TradingControlView(APIView):
    permission_classes = (IsAdminUser,)
    scope = TradingControl.Scope.PLATFORM
    state = TradingControl.State.HALTED

    @transaction.atomic
    def post(self, request, instrument=None):
        key = request.headers.get("Idempotency-Key", "")
        reason = str(request.data.get("reason", "")).strip()
        request_id = request.headers.get("X-Request-ID", "")
        if not key or not reason or not request_id:
            return error_response(request, "VALIDATION_ERROR", 400, {"required": ["Idempotency-Key", "reason", "X-Request-ID"]})
        scope_ref = instrument or "*"
        try:
            record, created = begin_idempotent_request(key=key, tenant_ref="platform", actor_ref=request.user.id, endpoint=request.path, method="POST", request_data=request.data)
        except IdempotencyConflict:
            return error_response(request, "IDEMPOTENCY_CONFLICT", 409)
        if not created and record.response_body is not None:
            return Response(record.response_body, status=record.response_status)
        control, _ = TradingControl.objects.update_or_create(scope=self.scope, scope_ref=scope_ref, defaults={"state": self.state, "reason": reason, "request_id": request_id, "changed_by_ref": str(request.user.id)})
        correlation_raw = str(getattr(request, "correlation_id", uuid.uuid4().hex))
        try:
            correlation_id = uuid.UUID(correlation_raw)
        except ValueError:
            correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, correlation_raw)
        ApplicationAuditEvent.objects.create(actor_ref=str(request.user.id), action=f"trading.control.{self.state.lower()}", resource_type="trading_control", resource_id=str(control.pk), request_id=request_id, correlation_id=correlation_id, context={"scope": self.scope, "scope_ref": scope_ref}, reason=reason, occurred_at=timezone.now())
        body = {"scope": self.scope, "scope_ref": scope_ref, "state": self.state}
        complete_idempotent_request(record, status=200, body=body, resource_type="trading_control", resource_id=control.pk)
        return Response(body)


class PlatformHaltView(TradingControlView):
    pass


class PlatformResumeView(TradingControlView):
    state = TradingControl.State.ACTIVE


class InstrumentHaltView(TradingControlView):
    scope = TradingControl.Scope.INSTRUMENT


class InstrumentResumeView(InstrumentHaltView):
    state = TradingControl.State.ACTIVE
