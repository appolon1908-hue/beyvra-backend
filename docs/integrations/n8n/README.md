# Trading backend ↔ Middleware ↔ n8n integration

## Financial safety decision

The trading backend owns trading, wallet, ledger, hold, deposit, withdrawal, transfer, compliance and reconciliation state. PostgreSQL is authoritative for financial state. n8n is not permitted to place trades, reserve or move funds, alter ledger entries, approve withdrawals, sign or broadcast transactions, call custody providers, call broker APIs or mutate balances.

```text
Trading/real-wallet durable event
  -> transactional outbox
  -> Middleware authenticated inbox
  -> safe automation job
  -> n8n notification, routing or human-review coordination
  -> governed Middleware command
  -> trading backend internal operation or task API
  -> read-back and reconciliation
```

## Allowed automation scope

n8n may coordinate only non-custodial, non-value-moving workflows such as:

```text
customer onboarding task routing
KYC/compliance review notification
risk and margin alert escalation
provider or ledger reconciliation exception assignment
stale operational task reminders
report generation requests
webhook delivery exception review
withdrawal approval reminder without approval authority
incident and audit notification
```

## Events available to automation

```text
trading.account.created
trading.account.review_required
trading.kyc.status_changed
trading.compliance.exception_created
trading.risk.alert_created
trading.margin.alert_created
trading.order.status_changed
trading.trade.status_changed
real_wallet.deposit.status_changed
real_wallet.withdrawal.requested
real_wallet.withdrawal.approval_pending
real_wallet.withdrawal.status_changed
real_wallet.transfer.status_changed
real_wallet.reconciliation.exception_created
real_wallet.webhook_delivery.failed
```

Only a minimum, redacted payload is supplied to n8n. Private keys, seed phrases, wallet secrets, provider credentials, full identity documents and sensitive financial payloads never enter workflows or Git.

## Commands allowed through Middleware

```text
trading.operations.create_task
trading.operations.assign_exception
trading.operations.request_report
trading.operations.request_reconciliation
trading.notification.request_internal
real_wallet.operations.create_review_task
real_wallet.operations.escalate_reconciliation_exception
real_wallet.operations.remind_approvers
real_wallet.webhook_delivery.request_retry_review
```

These commands cannot post a ledger entry, place an order, execute a trade, create a withdrawal, approve or reject a withdrawal, reserve/capture/release a hold, credit a deposit, transfer funds, sign a transaction or call custody/chain infrastructure.

## Prohibited commands

```text
trade.place
trade.cancel_live
wallet.balance.mutate
ledger.post
hold.reserve
hold.capture
hold.release
withdrawal.create
withdrawal.approve
withdrawal.reject
withdrawal.execute
transfer.execute
deposit.credit
custody.sign
chain.broadcast
provider.credential.rotate
```

## Initial n8n workflows

```text
trading.customer.onboarding-review.v1
trading.compliance.exception-route.v1
trading.risk.alert-escalate.v1
trading.margin.alert-escalate.v1
trading.order-status-notification.v1
real-wallet.withdrawal-approval-reminder.v1
real-wallet.reconciliation-exception.v1
real-wallet.webhook-delivery-exception.v1
```

## Approval and idempotency

- Withdrawal approval remains in the trading backend and requires its existing dual-approver rules.
- An initiator cannot approve their own withdrawal.
- n8n cannot manufacture, count or submit an approval decision.
- Financial mutation idempotency remains database backed in the trading backend.
- A provider timeout is an unknown outcome and requires reconciliation.
- Dead-letter replay cannot repeat a financial mutation.

## Capability freeze

```text
REAL_TRADING_EXECUTION=false
REAL_WALLET_READ=false unless separately approved
REAL_WALLET_DEPOSITS=false
REAL_WALLET_WITHDRAWALS=false
REAL_WALLET_TRANSFERS=false
REAL_WALLET_WEBHOOK_DELIVERY=false
CUSTODY_EXECUTION=false
CHAIN_BROADCAST=false
PAYMENT_EXECUTION=false
DEAD_LETTER_REPLAY=false
```

## Branch dependencies

```text
trading-backend/main
Middleware-/core/integration-contracts
Middleware-/core/event-ledger-outbox
Middleware-/core/webhook-inbox-replay
Middleware-/core/workers-scheduler
Middleware-/integration/keycloak
Middleware-/integration/n8n
N8N/contract/automation-control-plane-v2-20260827
N8N/shared/automation-runtime
N8N/automation/trading-operations
```

## Acceptance

```text
DIRECT_N8N_TRADING_API_ACCESS=DENIED
DIRECT_N8N_DATABASE_ACCESS=DENIED
DIRECT_N8N_CUSTODY_ACCESS=DENIED
N8N_FINANCIAL_APPROVAL_AUTHORITY=NO
N8N_VALUE_MOVEMENT_AUTHORITY=NO
FINANCIAL_PAYLOADS_IN_WORKFLOW_GIT=NONE
TENANT_ISOLATION=PASS
UNKNOWN_PROVIDER_OUTCOME_RECONCILED=PASS
LIVE_FINANCIAL_CAPABILITIES=DISABLED
WORKFLOWS_ACTIVE_IN_GIT=NO
PRODUCTION_CHANGED=NO
```
