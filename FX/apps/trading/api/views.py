from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.foundation.services import IdempotencyConflict
from apps.post_trade.api import trade_payload
from apps.post_trade.models import Trade
from apps.trading.application.context import TradingContext, context_error_code
from apps.trading.application.simulation import (
    account_for,
    cancel,
    create,
    position_order,
    preview,
    replace,
    serialize_account,
    serialize_order,
    simulation_authorized,
)
from apps.trading.models import SimulatedPosition, TradingOrder
from apps.valuation.portfolio_api import PortfolioSummaryView
from integrations.financial.simulated import SimulationFinancialError
from pricing_authority.models import FeeSchedule

from .errors import error_response
from .serializers import (
    AccountCollectionSerializer,
    OrderCollectionSerializer,
    OrderPreviewResponseSerializer,
    OrderRequestSerializer,
    OrderResponseSerializer,
    PaperAccountProjectionSerializer,
    PositionCollectionSerializer,
    PositionResponseSerializer,
    ReducePositionRequestSerializer,
    ReplaceOrderRequestSerializer,
    TradeCollectionSerializer,
    TradeResponseSerializer,
)


IDEMPOTENCY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True, description="Integer order version returned by the API.")
CORRELATION = OpenApiParameter("X-Correlation-ID", str, OpenApiParameter.HEADER, required=False)


def _guard(request):
    return None if simulation_authorized(request) else error_response(request, "FEATURE_DISABLED", 503)


def _context(request):
    try:
        return TradingContext.from_request(request)
    except Exception as error:
        raise ValueError(context_error_code(error))


def _failure(request, error):
    code = str(error)
    forbidden = {
        "KYC_REQUIRED", "KYC_PENDING", "KYC_REJECTED", "AML_REVIEW", "AML_BLOCKED",
        "SANCTIONS_REVIEW", "SANCTIONS_BLOCKED", "JURISDICTION_RESTRICTED", "ACCOUNT_RESTRICTED",
        "ACCOUNT_SUSPENDED", "TRADING_DISABLED", "MANUAL_REVIEW_REQUIRED", "COMPLIANCE_NOT_ELIGIBLE",
        "COMPLIANCE_RESTRICTED", "ORGANIZATION_NOT_AUTHORIZED", "ORGANIZATION_REQUIRED", "INVALID_ORGANIZATION",
    }
    validation = {
        "INVALID_SIDE", "INVALID_QUANTITY", "INVALID_QUANTITY_PRECISION", "INVALID_PRICE",
        "INVALID_PRICE_PRECISION", "LIMIT_PRICE_REQUIRED", "REPLACE_PRICE_ONLY", "INVALID_LOT_SIZE",
        "INVALID_TICK_SIZE", "MIN_QUANTITY_NOT_MET", "MAX_QUANTITY_EXCEEDED", "MIN_NOTIONAL_NOT_MET",
        "MAX_NOTIONAL_EXCEEDED", "INSTRUMENT_REQUIRED", "ORDER_TYPE_UNSUPPORTED",
        "INSTRUMENT_UNAVAILABLE", "INSTRUMENT_AMBIGUOUS", "POSITION_REDUCTION_EXCEEDS_AVAILABLE",
    }
    unavailable = {"PRICE_STALE", "PRICE_UNAVAILABLE", "PRICE_INVALID", "PROVIDER_UNAVAILABLE", "MARKET_CLOSED", "INSTRUMENT_RULES_UNAVAILABLE", "FEE_POLICY_UNAVAILABLE"}
    not_found = {"RESOURCE_NOT_FOUND", "TRADE_NOT_FOUND"}
    if code in not_found:
        status = 404
    elif code in forbidden:
        status = 403
    elif code == "TENANT_SELECTION_REQUIRED":
        status = 400
    elif code in validation:
        status = 422
    elif code in unavailable:
        status = 503
    elif code in {"IDEMPOTENCY_KEY_REQUIRED", "IF_MATCH_REQUIRED"}:
        status = 428
    else:
        status = 409
    return error_response(request, code, status)


def _position_payload(row):
    return {
        "id": str(row.id),
        "tenant_ref": row.account.tenant_ref,
        "account_ref": row.account.account_ref,
        "instrument": row.instrument_id,
        "quantity": str(row.quantity),
        "average_price": str(row.average_price),
        "realized_pnl": str(row.realized_pnl),
        "simulation": True,
    }


class OrderCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "order_create"

    @extend_schema(responses={200: OrderCollectionSerializer})
    def get(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            context = _context(request)
        except ValueError as error:
            return _failure(request, error)
        orders = TradingOrder.objects.filter(
            tenant_ref=context.tenant_ref,
            account_ref=context.account_ref,
            simulation=True,
        ).order_by("-created_at")
        return Response({"results": [serialize_order(order) for order in orders]})

    @extend_schema(
        parameters=[IDEMPOTENCY, CORRELATION],
        request=OrderRequestSerializer,
        responses={201: OrderResponseSerializer},
    )
    def post(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            body, status = create(_context(request), request.data, request.headers.get("Idempotency-Key"), getattr(request, "correlation_id", None))
            return Response(body, status=status)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error:
            return _failure(request, error)


class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "order_preview"

    @extend_schema(
        parameters=[CORRELATION],
        request=OrderRequestSerializer,
        responses={200: OrderPreviewResponseSerializer},
    )
    def post(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            return Response(preview(_context(request), request.data))
        except (ValueError, SimulationFinancialError) as error:
            return _failure(request, error)


class OrderDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OrderResponseSerializer})
    def get(self, request, order_id):
        if blocked := _guard(request):
            return blocked
        try:
            context = _context(request)
        except ValueError as error:
            return _failure(request, error)
        order = TradingOrder.objects.filter(
            pk=order_id,
            tenant_ref=context.tenant_ref,
            account_ref=context.account_ref,
            simulation=True,
        ).first()
        return Response(serialize_order(order)) if order else error_response(request, "RESOURCE_NOT_FOUND", 404)


class OrderCancelView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[IDEMPOTENCY, IF_MATCH, CORRELATION],
        request=None,
        responses={200: OrderResponseSerializer},
    )
    def post(self, request, order_id):
        if blocked := _guard(request):
            return blocked
        try:
            return Response(cancel(_context(request), order_id, request.headers.get("Idempotency-Key"), request.headers.get("If-Match"), getattr(request, "correlation_id", None)))
        except TradingOrder.DoesNotExist:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error:
            return _failure(request, error)


class OrderReplaceView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[IDEMPOTENCY, IF_MATCH, CORRELATION],
        request=ReplaceOrderRequestSerializer,
        responses={200: OrderResponseSerializer},
    )
    def post(self, request, order_id):
        if blocked := _guard(request):
            return blocked
        try:
            return Response(replace(_context(request), order_id, request.data, request.headers.get("Idempotency-Key"), request.headers.get("If-Match"), getattr(request, "correlation_id", None)))
        except TradingOrder.DoesNotExist:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error:
            return _failure(request, error)


class TradesView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: TradeCollectionSerializer})
    def get(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            context = _context(request)
        except ValueError as error:
            return _failure(request, error)
        rows = Trade.objects.filter(account_ref=context.account_ref, tenant_ref=context.tenant_ref).order_by("-trade_time")
        return Response({"results": [trade_payload(row) for row in rows]})


class TradeDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: TradeResponseSerializer})
    def get(self, request, trade_id):
        if blocked := _guard(request):
            return blocked
        try:
            context = _context(request)
        except ValueError as error:
            return _failure(request, error)
        row = Trade.objects.filter(pk=trade_id, account_ref=context.account_ref, tenant_ref=context.tenant_ref).first()
        return Response(trade_payload(row)) if row else error_response(request, "TRADE_NOT_FOUND", 404)


class PositionsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: PositionCollectionSerializer})
    def get(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            account = account_for(_context(request))
        except ValueError as error:
            return _failure(request, error)
        rows = SimulatedPosition.objects.select_related("account").filter(account=account).order_by("instrument_id")
        return Response({"results": [_position_payload(row) for row in rows]})


class PositionDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: PositionResponseSerializer})
    def get(self, request, position_id):
        if blocked := _guard(request):
            return blocked
        try:
            account = account_for(_context(request))
        except ValueError as error:
            return _failure(request, error)
        row = SimulatedPosition.objects.select_related("account").filter(pk=position_id, account=account).first()
        return Response(_position_payload(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class PositionCommandView(APIView):
    permission_classes = (IsAuthenticated,)
    command = "close"

    @extend_schema(
        parameters=[IDEMPOTENCY, CORRELATION],
        request=None,
        responses={201: OrderResponseSerializer},
    )
    def post(self, request, position_id):
        if blocked := _guard(request):
            return blocked
        try:
            body, status = position_order(
                _context(request),
                position_id,
                command=self.command,
                quantity=request.data.get("quantity"),
                idempotency_key=request.headers.get("Idempotency-Key"),
                correlation_id=getattr(request, "correlation_id", None),
            )
            return Response(body, status=status)
        except SimulatedPosition.DoesNotExist:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        except (ValueError, SimulationFinancialError, IdempotencyConflict) as error:
            return _failure(request, error)


class PositionCloseView(PositionCommandView):
    command = "close"


class PositionReduceView(PositionCommandView):
    command = "reduce"

    @extend_schema(
        parameters=[IDEMPOTENCY, CORRELATION],
        request=ReducePositionRequestSerializer,
        responses={201: OrderResponseSerializer},
    )
    def post(self, request, position_id):
        return super().post(request, position_id)


class AccountsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: AccountCollectionSerializer})
    def get(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            return Response({"results": [serialize_account(account_for(_context(request)))]})
        except ValueError as error:
            return _failure(request, error)


class AccountDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: PaperAccountProjectionSerializer})
    def get(self, request, account_id):
        if blocked := _guard(request):
            return blocked
        try:
            account = account_for(_context(request))
        except ValueError as error:
            return _failure(request, error)
        return Response(serialize_account(account)) if account.id == account_id else error_response(request, "RESOURCE_NOT_FOUND", 404)


class PortfolioView(PortfolioSummaryView):
    def get(self, request):
        response = super().get(request)
        if response.status_code == 200:
            response.data["buying_power"] = response.data["available_cash"]
            response.data["margin_if_applicable"] = None
        return response


class FeesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if blocked := _guard(request):
            return blocked
        try:
            _context(request)
        except ValueError as error:
            return _failure(request, error)
        rows = FeeSchedule.objects.filter(status="ACTIVE").order_by("priority", "code")
        return Response({
            "results": [{"code": row.code, "fee_type": row.fee_type, "currency": row.currency, "version": row.updated_at.isoformat(), "simulation": True} for row in rows],
            "real_trading_enabled": False,
        })
