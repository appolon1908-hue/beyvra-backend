# Instrument identity

Canonical identity is `instrument_id`, never a provider ticker. `InstrumentRegistry` carries symbol/display symbol, asset class, base/quote asset, venue, status, precisions, timezone, and an explicit provider-symbol map. Reverse lookup rejects duplicate mappings, unknown symbols, asset-class mismatch, and venue mismatch. Internal time is UTC while exchange timezone metadata is retained. Current static demo entries must migrate to durable reviewed reference records before production approval.

