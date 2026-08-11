from financial_client.client import FinancialServiceClient

from .exceptions import FinancialMutationDisabled


class FinancialClient:
    """Only supported application boundary to the independently deployed Financial Service."""
    def __init__(self, transport=None):
        self.transport = transport or FinancialServiceClient()

    def get_accounts(self, context):
        return self.transport.list_wallets(context)

    def get_balances(self, context, account_id):
        return self.transport.get_balances(context, account_id)

    def _disabled(self, *_args, **_kwargs):
        raise FinancialMutationDisabled("FEATURE_DISABLED")

    reserve_funds = _disabled
    release_reservation = _disabled
    settle_trade = _disabled
    quote_withdrawal = _disabled
    request_withdrawal = _disabled
    create_transfer = _disabled
    get_ledger_transaction = _disabled
    get_statement = _disabled
