from .common import POLICY_VERSION, audit, publish
from .models import SettlementInstruction
from .observability import SETTLEMENT_INSTRUCTIONS


class SettlementInstructionService:
    @classmethod
    def create_from_trade(cls, trade):
        obligations = {row.obligation_type: row for row in trade.obligations.all()}
        cash = obligations["CASH_DEBIT" if trade.side == "BUY" else "CASH_CREDIT"]
        asset = obligations["ASSET_RECEIPT" if trade.side == "BUY" else "ASSET_DELIVERY"]
        fee = obligations["FEE_DEBIT"]
        deliver_asset, deliver_quantity = ((cash.asset, cash.amount + fee.amount) if trade.side == "BUY" else (asset.asset, asset.quantity))
        receive_asset, receive_quantity = ((asset.asset, asset.quantity) if trade.side == "BUY" else (cash.asset, cash.amount - fee.amount))
        instruction, created = SettlementInstruction.objects.get_or_create(trade=trade, defaults={"account_ref": trade.account_ref, "instrument_id": trade.instrument_id, "settlement_type": "INTERNAL_SIMULATION", "settlement_date": trade.settlement_date, "deliver_asset": deliver_asset, "deliver_quantity": deliver_quantity, "receive_asset": receive_asset, "receive_quantity": receive_quantity, "currency": trade.trade_currency, "cash_amount": trade.gross_notional, "fee_amount": fee.amount, "idempotency_key": f"post-trade:{trade.id}:{POLICY_VERSION}", "policy_version": POLICY_VERSION, "simulation": True})
        if created:
            audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="settlement.instruction.created", resource_type="settlement_instruction", resource_ref=instruction.id, evidence={"trade_id": str(trade.id), "simulation": True})
            publish(trade=trade, event_type="post_trade.settlement.pending.v1", payload={"settlement_id": str(instruction.id), "state": instruction.state})
            SETTLEMENT_INSTRUCTIONS.labels("simulation", instruction.state).inc()
        cls.validate(instruction)
        return instruction, created

    @staticmethod
    def validate(instruction):
        if not instruction.simulation or instruction.deliver_quantity < 0 or instruction.receive_quantity < 0:
            raise ValueError("SETTLEMENT_INSTRUCTION_INVALID")
        return True

    @staticmethod
    def lookup(instruction_id, *, tenant_ref, account_ref=None):
        rows = SettlementInstruction.objects.filter(pk=instruction_id, trade__tenant_ref=tenant_ref)
        return rows.filter(account_ref=account_ref).first() if account_ref else rows.first()

    @staticmethod
    def cancel_if_permitted(instruction):
        if instruction.state not in {"SETTLEMENT_PENDING", "SETTLEMENT_INSTRUCTED"}:
            raise ValueError("SETTLEMENT_CANNOT_CANCEL")
        instruction.state = "CANCELLED"
        instruction.save(update_fields=("state", "updated_at"))
        return instruction
