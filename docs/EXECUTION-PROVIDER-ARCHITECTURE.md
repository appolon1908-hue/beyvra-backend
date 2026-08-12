# Execution provider architecture

`ExecutionProvider` defines health, capabilities, preview, submit, cancel, replace, lookup, list, and execution retrieval. `ExecutionRouter` evaluates mode, account eligibility, market freshness, incident state, instrument, provider capability, and policy.

Current authority is deterministic simulation. Requests for `PAPER` or `LIVE` fail closed. Provider routing policy is versioned by provider, asset class/venue, enabled state, priority, notional cap, order types, and staging/production approval. A timed-out submission is `UNKNOWN` until provider operation lookup resolves it; it must never be blindly submitted to another broker.

TradeStation SIM is a future paper candidate, not live certification. Alpaca and IBKR remain contract candidates. No adapter has credentials or activation authority here.

