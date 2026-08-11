from provider_governance.service import resolve_provider


def authorize_coinmarketcap(*, product, symbol="*"):
    return resolve_provider(
        provider_id="coinmarketcap", provider_type="MARKET_DATA", product=product,
        symbol=symbol, region="GLOBAL", caller_service="coinmarketcharts-api",
    )
