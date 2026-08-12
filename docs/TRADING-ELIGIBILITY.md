# Eligibility authority

`get_trading_eligibility`, `get_deposit_eligibility`, `get_withdrawal_eligibility`, and `get_transfer_eligibility` return `ALLOWED`, `DENIED`, or `REVIEW_REQUIRED`, stable reason codes, `compliance-2026-08-11.v1`, and evaluation time. Inputs are account, KYC, AML, sanctions, jurisdiction, review dates, expirations, and active restrictions. Unknown or missing data fails closed. Canonical simulation preview/create invokes the service and stores a decision snapshot. Real-value operations remain independently `FEATURE_DISABLED` even when policy returns allowed.
