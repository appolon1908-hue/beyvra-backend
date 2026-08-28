# Account and portfolio authority

Canonical endpoints expose account/session/security data and simulation trading accounts, positions, trades and orders. Portfolio summary, positions, allocation, performance, risk and evidence quality are owned by `/api/v1/portfolio/*`. The older `/api/portfolio/summary/` and `/api/v1/trading/portfolio` routes are deprecation-only aliases of the same canonical summary view; they contain no alternate balance or valuation logic.

Unknown valuations remain `null`; the backend does not fabricate market price, P&L, margin, or buying power. Simulation projections are isolated. Real wallet balances and settlement belong solely to Financial Service.
