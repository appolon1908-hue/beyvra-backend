# Account and portfolio authority

Canonical endpoints expose account/session/security data and simulation trading accounts, positions, trades, orders, and `/api/v1/trading/portfolio`. Portfolio fields include cash, buying power, equity, market value, P&L, optional margin, timestamp, and `simulation`.

Unknown valuations remain `null`; the backend does not fabricate market price, P&L, margin, or buying power. Simulation projections are isolated. Real wallet balances and settlement belong solely to Financial Service.

