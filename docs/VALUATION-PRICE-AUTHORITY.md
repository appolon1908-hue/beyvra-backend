# Valuation price authority

`ValuationPriceService` selects persisted market evidence using purpose-specific precedence. Intraday selection uses MID/LAST/BID/ASK; end-of-day selection uses official close, settlement price, or approved NAV price. Records carry provider reference, timestamp, market status, quality, and policy version.

Missing, invalid, unavailable, or stale evidence fails closed. Tests create explicit `fixture` evidence; the runtime does not invent prices. Historical selection uses the instrument UUID/reference, never a current ticker label.

