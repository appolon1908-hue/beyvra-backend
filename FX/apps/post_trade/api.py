from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.api.errors import error_response

from .capture import TradeCaptureService
from .exceptions import PostTradeExceptionService
from .models import PostTradeException, SettlementInstruction, TradeConfirmation, TradePositionEffect
from .reconciliation import PositionReconciler


def account_ref(request): return f"sim:{request.user.pk}"


def trade_payload(row):
    return {"id": str(row.id), "trade_id": str(row.id), "order_id": str(row.order_id), "execution_id": row.execution_id, "instrument_id": row.instrument_id, "instrument": row.instrument_id, "side": row.side, "quantity": str(row.quantity), "price": str(row.price), "gross_notional": str(row.gross_notional), "fee": str(row.fee_snapshot.total_fee), "currency": row.trade_currency, "trade_time": row.trade_time.isoformat(), "executed_at": row.trade_time.isoformat(), "settlement_date": row.settlement_date.isoformat(), "state": row.trade_state, "execution_mode": row.execution_mode, "simulation": row.simulation}


def settlement_payload(row):
    return {"id": str(row.id), "trade_id": str(row.trade_id), "instrument_id": row.instrument_id, "settlement_type": row.settlement_type, "settlement_date": row.settlement_date.isoformat(), "deliver_asset": row.deliver_asset, "deliver_quantity": str(row.deliver_quantity), "receive_asset": row.receive_asset, "receive_quantity": str(row.receive_quantity), "currency": row.currency, "cash_amount": str(row.cash_amount), "fee_amount": str(row.fee_amount), "state": row.state, "simulation": row.simulation}


def confirmation_payload(row):
    return {"id": str(row.id), "trade_id": str(row.trade_id), "confirmation_number": row.confirmation_number, "version": row.version, "trade_date": row.trade_date.isoformat(), "settlement_date": row.settlement_date.isoformat(), "instrument": row.instrument_snapshot, "side": row.side, "quantity": str(row.quantity), "price": str(row.price), "gross_notional": str(row.gross_notional), "fees": str(row.fees), "net_amount": str(row.net_amount), "currency": row.currency, "venue": row.venue_safe, "execution_mode": row.execution_mode, "status": row.status}


class CustomerCollection(APIView):
    permission_classes = (IsAuthenticated,)
    model = None; serializer = staticmethod(lambda row: {})
    def get(self, request):
        rows = self.model.objects.filter(account_ref=account_ref(request), trade__tenant_ref="default").order_by("-trade__trade_time", "-id")
        return Response({"results": [self.serializer(row) for row in rows]})


class CustomerDetail(CustomerCollection):
    def get(self, request, resource_id):
        row = self.model.objects.filter(pk=resource_id, account_ref=account_ref(request), trade__tenant_ref="default").first()
        return Response(self.serializer(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class SettlementList(CustomerCollection): model = SettlementInstruction; serializer = staticmethod(settlement_payload)
class SettlementDetail(CustomerDetail): model = SettlementInstruction; serializer = staticmethod(settlement_payload)
class ConfirmationList(CustomerCollection): model = TradeConfirmation; serializer = staticmethod(confirmation_payload)
class ConfirmationDetail(CustomerDetail): model = TradeConfirmation; serializer = staticmethod(confirmation_payload)


class PositionEffectList(CustomerCollection):
    model = TradePositionEffect
    serializer = staticmethod(lambda row: {"id": str(row.id), "trade_id": str(row.trade_id), "instrument_id": row.instrument_id, "quantity_delta": str(row.quantity_delta), "cost_basis_delta": str(row.cost_basis_delta), "effect_type": row.effect_type, "applied_at": row.applied_at.isoformat(), "simulation": row.simulation})


class PositionEffectDetail(CustomerDetail): model = TradePositionEffect; serializer = PositionEffectList.serializer


class ReconciliationStatus(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request): return Response({"status": PositionReconciler.run(tenant_ref="default", persist=False)["status"], "simulation": True})


class PostTradeRole(BasePermission):
    roles = ("post_trade_viewer", "post_trade_analyst", "post_trade_manager", "platform_admin")
    def has_permission(self, request, view): return request.user.is_authenticated and (request.user.is_superuser or request.user.groups.filter(name__in=self.roles).exists())


class AnalystRole(PostTradeRole): roles = ("post_trade_analyst", "post_trade_manager", "platform_admin")
class ManagerRole(PostTradeRole): roles = ("post_trade_manager", "platform_admin")


class OperatorTrades(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request, trade_id=None):
        if trade_id:
            row = TradeCaptureService.get_trade(trade_id, tenant_ref="default")
            return Response(trade_payload(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"results": [trade_payload(row) for row in TradeCaptureService.list_trades(tenant_ref="default")]})


class OperatorSettlements(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request, settlement_id=None):
        rows = SettlementInstruction.objects.filter(trade__tenant_ref="default")
        if settlement_id:
            row = rows.filter(pk=settlement_id).first(); return Response(settlement_payload(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"results": [settlement_payload(row) for row in rows.order_by("-created_at")]})


class OperatorConfirmations(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request): return Response({"results": [confirmation_payload(row) for row in TradeConfirmation.objects.filter(trade__tenant_ref="default").order_by("-generated_at")]})


class OperatorExceptions(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request, exception_id=None):
        rows = PostTradeException.objects.filter(tenant_ref="default")
        if exception_id:
            row = rows.filter(pk=exception_id).first(); return Response({"id": str(row.id), "type": row.exception_type, "severity": row.severity, "state": row.state}) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"results": [{"id": str(row.id), "type": row.exception_type, "severity": row.severity, "state": row.state} for row in rows.order_by("-detected_at")]})


class ExceptionAction(APIView):
    permission_classes = (IsAuthenticated, AnalystRole); action = "assign"
    def post(self, request, exception_id):
        row = PostTradeException.objects.filter(pk=exception_id, tenant_ref="default").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        try:
            if self.action == "assign": PostTradeExceptionService.assign(row, actor_ref=str(request.user.pk))
            elif self.action == "escalate": PostTradeExceptionService.escalate(row, actor_ref=str(request.user.pk))
            else: PostTradeExceptionService.resolve(row, actor_ref=str(request.user.pk), resolution_code=str(request.data.get("resolution_code", "REVIEWED")))
        except ValueError as exc: return error_response(request, str(exc), 403)
        row.refresh_from_db(); return Response({"id": str(row.id), "state": row.state})


class ExceptionAssign(ExceptionAction): action = "assign"
class ExceptionEscalate(ExceptionAction): action = "escalate"
class ExceptionResolve(ExceptionAction): permission_classes = (IsAuthenticated, ManagerRole); action = "resolve"


class OperatorReconciliation(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request): return Response(PositionReconciler.run(tenant_ref="default", persist=False))
    def post(self, request):
        if not AnalystRole().has_permission(request, self): return error_response(request, "PERMISSION_DENIED", 403)
        return Response(PositionReconciler.run(tenant_ref="default", persist=True))


class OperatorEvidence(APIView):
    permission_classes = (IsAuthenticated, PostTradeRole)
    def get(self, request, trade_id):
        trade = TradeCaptureService.get_trade(trade_id, tenant_ref="default")
        if not trade: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"trade": trade_payload(trade), "allocations": [str(row.id) for row in trade.allocations.all()], "obligations": [str(row.id) for row in trade.obligations.all()], "settlement_instruction": str(trade.settlement_instruction.id), "confirmations": [str(row.id) for row in trade.confirmations.all()], "position_effects": [str(row.id) for row in trade.position_effects.all()], "simulation": True})
