from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.trading.application.simulation import account_for, cancel, create, preview, serialize_account, serialize_order, simulation_authorized
from apps.trading.models import SimulatedPosition, SimulatedTrade, TradingOrder
from apps.post_trade.api import trade_payload
from apps.post_trade.models import Trade
from apps.foundation.services import IdempotencyConflict
from integrations.financial.simulated import SimulationFinancialError
from .errors import error_response


def _guard(request):
    return None if simulation_authorized(request) else error_response(request, "FEATURE_DISABLED", 503)


def _failure(request, error):
    code = str(error)
    compliance_codes = {"KYC_REQUIRED", "KYC_PENDING", "KYC_REJECTED", "AML_REVIEW", "AML_BLOCKED", "SANCTIONS_REVIEW", "SANCTIONS_BLOCKED", "JURISDICTION_RESTRICTED", "ACCOUNT_RESTRICTED", "ACCOUNT_SUSPENDED", "TRADING_DISABLED", "MANUAL_REVIEW_REQUIRED", "COMPLIANCE_NOT_ELIGIBLE"}
    status = 409 if code in {"ORDER_INVALID_STATE", "IDEMPOTENCY_CONFLICT"} else 422 if code == "VALIDATION_ERROR" else 403 if code == "SIMULATION_AUTHORITY_REQUIRED" or code in compliance_codes else 409
    return error_response(request, code, status)


class OrderCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "order_create"
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        orders = TradingOrder.objects.filter(subject_ref=str(request.user.pk), tenant_ref="default", simulation=True).order_by("-created_at")
        return Response({"results": [serialize_order(order) for order in orders]})
    def post(self, request):
        if blocked := _guard(request): return blocked
        key = request.headers.get("Idempotency-Key")
        if not key: return error_response(request, "VALIDATION_ERROR", 422)
        try:
            body, status = create(request.user, request.data, key, getattr(request,"correlation_id",None))
            return Response(body, status=status)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error:
            return _failure(request, error)


class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "order_preview"
    def post(self, request):
        if blocked := _guard(request): return blocked
        try: return Response(preview(request.user, request.data))
        except (ValueError, SimulationFinancialError) as error: return _failure(request, error)


class OrderDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        if not simulation_authorized(request): return error_response(request, "RESOURCE_NOT_FOUND", 404)
        order = TradingOrder.objects.filter(pk=order_id, subject_ref=str(request.user.pk), tenant_ref="default", simulation=True).first()
        return Response(serialize_order(order)) if order else error_response(request, "RESOURCE_NOT_FOUND", 404)


class OrderCancelView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request, order_id):
        if blocked := _guard(request): return blocked
        try: return Response(cancel(request.user, order_id))
        except TradingOrder.DoesNotExist: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        except (ValueError, SimulationFinancialError) as error: return _failure(request, error)


class OrderReplaceView(APIView):
    """Replace is contract-ready but unavailable until independently certified."""
    permission_classes = (IsAuthenticated,)
    def post(self, request, order_id):
        if blocked := _guard(request): return blocked
        return error_response(request, "CAPABILITY_UNSUPPORTED", 409)


class TradesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        rows = Trade.objects.filter(account_ref=f"sim:{request.user.pk}", tenant_ref="default").order_by("-trade_time")
        return Response({"results": [trade_payload(row) for row in rows]})


class TradeDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, trade_id):
        row = Trade.objects.filter(pk=trade_id, account_ref=f"sim:{request.user.pk}", tenant_ref="default").first()
        return Response(trade_payload(row)) if row else error_response(request, "TRADE_NOT_FOUND", 404)


class PositionsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        rows = SimulatedPosition.objects.filter(account__subject_ref=str(request.user.pk), account__tenant_ref="default")
        return Response({"results": [{"id": str(row.id), "instrument": row.instrument_id, "quantity": str(row.quantity), "average_price": str(row.average_price), "realized_pnl": str(row.realized_pnl), "simulation": True} for row in rows]})


class AccountsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        return Response({"results": [serialize_account(account_for(request.user))]})


class PortfolioView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        if not simulation_authorized(request):
            return Response({"cash": "0", "buying_power": "0", "equity": "0", "market_value": "0", "unrealized_pnl": "0", "realized_pnl": "0", "margin_if_applicable": None, "positions": [], "simulation": True})
        account = account_for(request.user)
        positions = list(SimulatedPosition.objects.filter(account=account))
        serialized = [{"instrument_id": row.instrument_id, "quantity": str(row.quantity), "average_entry_price": str(row.average_price), "market_price": None, "market_value": None, "unrealized_pnl": None, "realized_pnl": str(row.realized_pnl), "updated_at": row.updated_at.isoformat(), "simulation": True} for row in positions]
        return Response({
            "cash": serialize_account(account)["available"], "buying_power": serialize_account(account)["available"],
            "equity": str(account.total_balance), "market_value": None, "unrealized_pnl": None,
            "realized_pnl": str(sum((row.realized_pnl for row in positions), 0)),
            "margin_if_applicable": None, "as_of": account.updated_at.isoformat(),
            "positions": serialized, "simulation": True,
        })


class EmptyDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, **kwargs): return error_response(request, "RESOURCE_NOT_FOUND", 404)


class FeesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request): return Response({"results": [{"rate": "0.001", "simulation": True}], "real_trading_enabled": False})
