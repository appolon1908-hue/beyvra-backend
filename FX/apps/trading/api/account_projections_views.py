from decimal import Decimal
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.application.simulation import account_for, serialize_account, simulation_authorized
from apps.trading.models import SimulatedAccount
from apps.post_trade.api import trade_payload
from apps.valuation.models import TaxLot
from apps.post_trade.models import Trade
from apps.trading.api.errors import error_response
from integrations.financial.simulated import SimulatedFinancialAdapter


def _available_and_reserved_cash(account):
    available_cash = SimulatedFinancialAdapter.available_quote(account)
    settled_cash = account.total_balance - account.pending_balance
    reserved_cash = settled_cash - available_cash
    if reserved_cash < Decimal("0"):
        reserved_cash = Decimal("0")
    return available_cash, reserved_cash


class AccountDetailProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response(serialize_account(account))


class AccountBalancesProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)

        total_cash = account.total_balance
        available_cash, reserved_cash = _available_and_reserved_cash(account)
        settled_cash = total_cash - reserved_cash
        unsettled_cash = Decimal("0.00")

        return Response({
            "account_id": str(account.id),
            "currency": account.quote_currency,
            "cash": str(total_cash),
            "settled_cash": str(settled_cash),
            "unsettled_cash": str(unsettled_cash),
            "reserved_cash": str(reserved_cash),
            "available_cash": str(available_cash),
            "buying_power": str(available_cash),
            "as_of": timezone.now().isoformat(),
            "quality": "COMPLETE"
        })


class AccountBuyingPowerProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)

        available_cash, _reserved_cash = _available_and_reserved_cash(account)
        return Response({
            "account_id": str(account.id),
            "currency": account.quote_currency,
            "buying_power": str(available_cash),
            "cash_available_for_trade": str(available_cash),
            "cash_available_for_withdrawal": str(available_cash),
            "as_of": timezone.now().isoformat(),
            "quality": "COMPLETE"
        })


class AccountTransactionsProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)

        trades = Trade.objects.select_related("fee_snapshot").filter(account_ref=account.account_ref, tenant_ref=account.tenant_ref).order_by("-trade_time")
        items = [
            {
                **trade_payload(t),
                "id": str(t.id),
                "type": "TRADE",
                "instrument_id": t.instrument_id,
                "amount": str(t.gross_notional),
                "fee": str(t.fee_snapshot.total_fee),
                "timestamp": t.trade_time.isoformat(),
                "status": t.trade_state,
            }
            for t in trades
        ]
        return Response({"results": items, "next_cursor": None, "has_more": False})


class AccountStatementsProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)

        return Response({
            "results": [
                {
                    "statement_id": "stmt_current",
                    "period_start": timezone.now().replace(day=1).isoformat(),
                    "period_end": timezone.now().isoformat(),
                    "currency": account.quote_currency,
                    "closing_balance": str(account.total_balance),
                    "download_ref": f"/api/v1/accounts/{account.id}/statements/stmt_current/download"
                }
            ]
        })


class AccountTaxLotsProjectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, account_id):
        if not simulation_authorized(request):
            return error_response(request, "RESOURCE_NOT_FOUND", 404)
        account = SimulatedAccount.objects.filter(pk=account_id, subject_ref=str(request.user.pk), tenant_ref="default").first()
        if not account:
            return error_response(request, "RESOURCE_NOT_FOUND", 404)

        lots = TaxLot.objects.filter(account_ref=account.account_ref, tenant_ref=account.tenant_ref).order_by("-acquisition_date", "-created_at")
        items = [
            {
                "lot_id": str(lot.id),
                "instrument_id": lot.instrument_id,
                "acquired_at": lot.acquisition_date.isoformat(),
                "quantity": str(lot.original_quantity),
                "cost_basis_per_unit": str(lot.unit_cost),
                "total_cost_basis": str(lot.total_cost),
                "disposed_quantity": str(lot.original_quantity - lot.remaining_quantity),
            }
            for lot in lots
        ]
        return Response({"results": items, "next_cursor": None, "has_more": False})
