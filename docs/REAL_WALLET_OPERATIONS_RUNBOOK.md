# Real Wallet Operations Runbook

## Before activation

- Confirm `real_wallet_*`, trading, and external-execution flags are false.
- Confirm no production provider credentials are present in application
  environment or logs.
- Confirm backup and restore evidence, alert routing, and migration head.

## Provider webhook failure

Inspect `real_integration_provider_webhook_receipts` by provider connection and
status. Retry only through the worker after signature verification. Keep the
connection disabled when provider identity or signature validation fails.

## Reconciliation exception

Run the reconciliation task with a provider snapshot. Do not mutate balances
to make a mismatch disappear. Escalate `AMOUNT_MISMATCH`, `MISSING_EXTERNAL`,
or `MISSING_INTERNAL` items for controlled review.

## Suspected withdrawal issue

Disable the affected asset/network flag, preserve holds and ledger entries,
and use compensating transactions only through an approved operator workflow.
Never edit posted entries or balances directly.
