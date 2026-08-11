# Provider adapters

Adapters must expose normalized historical candles, quotes, ticks, status, and
optional order-book/trade feeds. Unsupported capabilities are explicit rather
than silently emulated. Provider credentials are injected through protected
staging configuration and never placed in frontend bundles.
