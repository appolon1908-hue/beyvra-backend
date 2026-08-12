# Cost basis, tax lots, and P&L

The simulation policy is explicitly `SIMULATION_FIFO_V1`. A canonical BUY opens one idempotent trade lot including its fee snapshot. A SELL locks eligible lots in acquisition order, creates immutable dispositions, and creates one realized-P&L event per disposal trade. Insufficient lots is an exception; no basis is fabricated.

Cost basis is rebuilt from remaining lot quantities plus explicit corporate-action adjustments. Unrealized P&L uses current approved valuation evidence minus remaining basis. This is economic simulation accounting, not jurisdictional tax advice or an official tax filing.

Supported model vocabulary includes FIFO, LIFO, HIFO, average-cost-where-valid, and specific identification; only the explicitly selected simulation FIFO policy is active. Changing selection policy requires a new version and must not rewrite prior dispositions.

