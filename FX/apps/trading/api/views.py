from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.trading.application.simulation import account_for, cancel, create, preview, serialize_account, serialize_order, simulation_authorized
from apps.trading.models import SimulatedPosition, SimulatedTrade, TradingOrder
from apps.foundation.models import OutboxEvent
from apps.post_trade.api import trade_payload
from apps.post_trade.models import Trade
from apps.foundation.services import IdempotencyConflict
from integrations.financial.simulated import SimulationFinancialError
from .errors import error_response
from apps.valuation.portfolio_api import PortfolioSummaryView
from .serializers import AccountCollectionSerializer


def _canonical_contract(request):
    return request.path.startswith("/api/v1/") and not request.path.startswith("/api/v1/trading/")


def _canonical_order_payload(order):
    return {
        "order_id": str(order.id),
        "account_id": order.account_ref,
        "instrument_id": order.instrument_id,
        "side": order.side,
        "order_type": order.order_type,
        "quantity": str(order.quantity),
        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
        "stop_price": str(order.stop_price) if order.stop_price is not None else None,
        "time_in_force": "DAY",
        "status": "CANCELED" if order.state == "CANCELLED" else order.state,
        "filled_quantity": str(order.filled_quantity),
        "average_fill_price": str(order.average_fill_price) if order.average_fill_price is not None else None,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _order_payload_for_request(order, request):
    if _canonical_contract(request):
        return _canonical_order_payload(order)
    return serialize_order(order)


def _execution_payload(trade):
    return {
        "execution_id": trade.execution_id,
        "order_id": str(trade.order_id),
        "account_id": trade.order.account_ref,
        "instrument_id": trade.instrument_id,
        "quantity": str(trade.quantity),
        "price": str(trade.price),
        "fee": str(trade.fee),
        "executed_at": trade.executed_at.isoformat(),
        "provider_reference": trade.execution_id,
    }


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
        return Response({"results": [_order_payload_for_request(order, request) for order in orders]})
    def post(self, request):
        if blocked := _guard(request): return blocked
        key = request.headers.get("Idempotency-Key")
        if not key: return error_response(request, "VALIDATION_ERROR", 422)
        try:
            body, status = create(request.user, request.data, key, getattr(request,"correlation_id",None))
            if _canonical_contract(request) and 200 <= status < 300:
                order = TradingOrder.objects.get(pk=body["id"], subject_ref=str(request.user.pk), tenant_ref="default", simulation=True)
                body = _canonical_order_payload(order)
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
        return Response(_order_payload_for_request(order, request)) if order else error_response(request, "RESOURCE_NOT_FOUND", 404)


class OrderCancelView(APIView):
    permission_classes = (IsAuthenticated,)
    @extend_schema(parameters=[
        OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
        OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True, description="Order version returned by the API."),
    ])
    def post(self, request, order_id):
        if blocked := _guard(request): return blocked
        key = request.headers.get("Idempotency-Key")
        expected_version = request.headers.get("If-Match")
        if not key or not expected_version:
            return error_response(request, "VALIDATION_ERROR", 422, {"required": ["Idempotency-Key", "If-Match"]})
        try:
            body = cancel(request.user, order_id, key, expected_version, getattr(request, "correlation_id", None))
            if _canonical_contract(request):
                order = TradingOrder.objects.get(pk=body["id"], subject_ref=str(request.user.pk), tenant_ref="default", simulation=True)
                body = _canonical_order_payload(order)
            return Response(body)
        except TradingOrder.DoesNotExist: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error: return _failure(request, error)


class OrderEventsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        if not simulation_authorized(request): return error_response(request, "RESOURCE_NOT_FOUND", 404)
        order = TradingOrder.objects.filter(pk=order_id, subject_ref=str(request.user.pk), tenant_ref="default", simulation=True).first()
        if not order: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        events = OutboxEvent.objects.filter(aggregate_type="order", aggregate_id=str(order.id)).order_by("created_at")
        results = [
            {
                "event_id": str(evt.event_id),
                "order_id": str(order.id),
                "event_type": evt.event_type,
                "sequence": idx + 1,
                "occurred_at": evt.created_at.isoformat(),
                "payload": evt.payload,
            }
            for idx, evt in enumerate(events)
        ]
        return Response({"results": results})


class ExecutionsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        trades = SimulatedTrade.objects.select_related("order").filter(order__subject_ref=str(request.user.pk), order__tenant_ref="default").order_by("-executed_at")
        if _canonical_contract(request):
            results = [_execution_payload(t) for t in trades]
        else:
            results = [
                {
                    "trade_id": str(t.trade_id),
                    "order_id": str(t.order_id),
                    "execution_id": t.execution_id,
                    "instrument_id": t.instrument_id,
                    "side": t.side,
                    "quantity": str(t.quantity),
                    "price": str(t.price),
                    "fee": str(t.fee),
                    "executed_at": t.executed_at.isoformat(),
                    "simulation": t.simulation,
                }
                for t in trades
            ]
        return Response({"results": results})


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
    @extend_schema(responses={200: AccountCollectionSerializer})
    def get(self, request):
        if not simulation_authorized(request): return Response({"results": []})
        return Response({"results": [serialize_account(account_for(request.user))]})


class PortfolioView(PortfolioSummaryView):
    """Keep legacy presentation fields without a second valuation authority."""

    def get(self, request):
        response = super().get(request)
        if response.status_code == 200:
            response.data["buying_power"] = response.data["available_cash"]
            response.data["margin_if_applicable"] = None
        return response


class EmptyDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, **kwargs): return error_response(request, "RESOURCE_NOT_FOUND", 404)


class FeesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request): return Response({"results": [{"rate": "0.001", "simulation": True}], "real_trading_enabled": False})
