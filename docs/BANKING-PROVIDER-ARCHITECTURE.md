# Banking provider architecture

`BankingProvider` separates account linking/verification from funding operations. `PaymentRailProvider` covers funding intent/status and payout/status. Plaid and Stripe are unapproved candidates only.

Every future mutation needs idempotency, signed webhook inbox handling, operation lookup after timeout, reconciliation, audit, provider governance, and Financial Service coordination. Deposits, payouts, and production providers remain disabled.

