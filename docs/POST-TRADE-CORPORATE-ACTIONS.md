# Corporate Actions and Post-Trade History

Canonical trades retain immutable `instrument_id` and confirmations retain historical display snapshots. Symbol changes, splits, delistings, and mergers must use reference-data lineage or adjusted views; raw trade quantity, price, and instrument are never rewritten. An unclear impact opens `CORPORATE_ACTION_CONFLICT`.
