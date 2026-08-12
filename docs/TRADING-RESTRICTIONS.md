# Trading Restrictions

Restrictions are tenant-scoped, effective-dated and cover account, tenant, canonical instrument, asset class, venue, or jurisdiction. Supported actions include block-new, cancel-only, close-only, side blocks, scope blocks, and review-required.

High-impact restrictions use maker/checker: one surveillance manager requests and a different manager approves. Removal must also be independent of the approving actor. Customer responses use `TRADING_NOT_AVAILABLE` or `ACCOUNT_REVIEW_REQUIRED`; reason codes and membership remain internal.
