"""Simulation-only financial contract. Never imports or contacts Financial Service."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.trading.models import SimulatedAccount, SimulatedPosition, SimulatedReservation


class SimulationFinancialError(ValueError):
    pass


class SimulatedFinancialAdapter:
    fee_rate = Decimal("0.001")

    @staticmethod
    def available_quote(account):
        reserved = account.reservations.filter(state=SimulatedReservation.State.ACTIVE, asset=account.quote_currency).aggregate(total=Sum("remaining_amount"))["total"] or Decimal("0")
        return account.total_balance - account.pending_balance - reserved

    @transaction.atomic
    def reserve_funds(self, *, account, order_id, instrument_id, side, quantity, price):
        account = SimulatedAccount.objects.select_for_update().get(pk=account.pk)
        quantity, price = Decimal(quantity), Decimal(price)
        if side == "BUY":
            amount, asset = quantity * price * (Decimal("1") + self.fee_rate), account.quote_currency
            if self.available_quote(account) < amount:
                raise SimulationFinancialError("INSUFFICIENT_AVAILABLE_BALANCE")
        else:
            asset = instrument_id.split("-")[0]
            position = SimulatedPosition.objects.select_for_update().filter(account=account, instrument_id=instrument_id).first()
            already = account.reservations.filter(state=SimulatedReservation.State.ACTIVE, asset=asset).aggregate(total=Sum("remaining_amount"))["total"] or Decimal("0")
            if not position or position.quantity - already < quantity:
                raise SimulationFinancialError("INSUFFICIENT_AVAILABLE_POSITION")
            amount = quantity
        reservation, created = SimulatedReservation.objects.get_or_create(order_id=order_id, defaults={"account": account, "asset": asset, "original_amount": amount, "remaining_amount": amount})
        if not created:
            raise SimulationFinancialError("DUPLICATE_RESERVATION")
        return reservation

    @transaction.atomic
    def release_reservation(self, reservation):
        reservation = SimulatedReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.state == SimulatedReservation.State.ACTIVE:
            reservation.remaining_amount = Decimal("0")
            reservation.state = SimulatedReservation.State.RELEASED
            reservation.save(update_fields=("remaining_amount", "state", "updated_at"))
        return reservation

    def settle_trade(self, *, reservation, side, instrument_id, quantity, price, fee):
        reservation = SimulatedReservation.objects.select_for_update().get(pk=reservation.pk)
        account = SimulatedAccount.objects.select_for_update().get(pk=reservation.account_id)
        quantity, price, fee = Decimal(quantity), Decimal(price), Decimal(fee)
        position, _ = SimulatedPosition.objects.select_for_update().get_or_create(account=account, instrument_id=instrument_id)
        if side == "BUY":
            debit = quantity * price + fee
            if reservation.remaining_amount < debit:
                raise SimulationFinancialError("RESERVATION_UNDERFUNDED")
            new_quantity = position.quantity + quantity
            position.average_price = ((position.quantity * position.average_price) + (quantity * price)) / new_quantity
            position.quantity = new_quantity
            account.total_balance -= debit
            reservation.remaining_amount -= debit
        else:
            if position.quantity < quantity or reservation.remaining_amount < quantity:
                raise SimulationFinancialError("INSUFFICIENT_AVAILABLE_POSITION")
            position.realized_pnl += (price - position.average_price) * quantity - fee
            position.quantity -= quantity
            account.total_balance += quantity * price - fee
            reservation.remaining_amount -= quantity
            if position.quantity == 0:
                position.average_price = Decimal("0")
        if reservation.remaining_amount == 0:
            reservation.state = SimulatedReservation.State.CONSUMED
        position.save()
        account.save(update_fields=("total_balance", "updated_at"))
        reservation.save(update_fields=("remaining_amount", "state", "updated_at"))
        return account, position, reservation
