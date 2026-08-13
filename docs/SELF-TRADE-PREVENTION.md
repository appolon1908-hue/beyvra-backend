# Self-Trade Prevention

Default certification mode is `REJECT_NEW`. The economic-owner key is the canonical simulation `account_ref`, not username. Active opposite orders in the same tenant, account and instrument are checked for a crossing price before a new order is stored.

Linked beneficial-owner groups are not available: `BENEFICIAL_OWNER_LINKAGE=EXTERNAL_DATA_REQUIRED`. No linkage is inferred. Future `CANCEL_OLD`, `CANCEL_BOTH`, and `ALLOW_WITH_ALERT` modes require separately versioned policy and tests.
