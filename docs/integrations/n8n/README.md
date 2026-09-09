# Beyvra backend ↔ governed n8n automation

## Authority boundary

Beyvra is a financial trading platform. This repository remains authoritative for its application, tenant, compliance, notification, reporting, demo-trading, trading, wallet and financial records.

n8n is restricted to **non-financial orchestration**. It may coordinate onboarding, compliance reminders, support tasks, internal alerts, report readiness, notification delivery and reconciliation through Codestra Middleware. It may not execute or approve trading, wallet, ledger, custody, deposit, withdrawal, transfer, payment, balance or provider actions.

```text
Beyvra domain event
  -> Beyvra signed delivery/outbox
  -> Middleware durable inbox
  -> canonical event + automation job
  -> private n8n wake and atomic claim
  -> n8n timing, branching or approval coordination
  -> governed Middleware command
  -> Beyvra backend operation adapter
  -> Beyvra read-back
  -> Middleware reconciliation
  -> frontend status projection when appropriate
```

Public callbacks never terminate directly at n8n. n8n receives no Beyvra database, Django administration, broker, Stripe, wallet, custody, market-data or provider credentials.

## Workflow family and identity

```text
workflow_family = product.beyvra-nonfinancial
machine_client  = n8n-product-automation
command_scope   = automation.command.product
command_prefix  = beyvra.operations.
```

The product client is additionally constrained by Middleware to this workflow family and prefix. A generic product scope alone must not authorize another product family.

## Allowed event families

```text
beyvra.account.onboarding_started
beyvra.account.onboarding_completed
beyvra.account.status_changed
beyvra.compliance.review_required
beyvra.compliance.document_missing
beyvra.compliance.review_completed
beyvra.support.case_created
beyvra.support.case_escalated
beyvra.notification.delivery_failed
beyvra.notification.preference_changed
beyvra.webhook.delivery_failed
beyvra.webhook.dead_lettered
beyvra.report.requested
beyvra.report.ready
beyvra.security.alert_created
beyvra.demo.session_milestone
```

Events contain safe identifiers and metadata only. Passwords, MFA material, API keys, broker credentials, Stripe secrets, wallet secrets, raw identity documents, complete financial statements, full trade payloads and provider tokens are prohibited.

## Allowed governed command families

```text
beyvra.operations.onboarding-task.create.v1
beyvra.operations.compliance-reminder.request.v1
beyvra.operations.support-escalation.create.v1
beyvra.operations.internal-alert.request.v1
beyvra.operations.notification.request.v1
beyvra.operations.report-generation.request.v1
beyvra.operations.report-status.read.v1
beyvra.operations.webhook-delivery.read.v1
beyvra.operations.webhook-retry.request.v1
beyvra.operations.crm-projection.request.v1
```

Every command must carry the active automation job, lease, execution, workflow and step identity. Middleware derives the authoritative tenant and actor from the job and checks the command prefix, scope, capability, idempotency key and semantic request fingerprint.

## Explicitly prohibited automation effects

```text
trade.place
trade.modify
trade.cancel_live
trade.close
order.submit
order.execute
wallet.create
wallet.balance.mutate
wallet.deposit
wallet.withdraw
wallet.transfer
ledger.post
hold.reserve
hold.capture
hold.release
payment.charge
payment.refund
withdrawal.create
withdrawal.approve
withdrawal.reject
withdrawal.execute
deposit.credit
transfer.execute
custody.sign
chain.broadcast
broker.credential.read
provider.credential.read
```

The prohibition includes both direct n8n calls and indirect commands disguised as generic product operations. n8n must not submit simulated/demo orders either; demo-trading actions remain user/backend domain operations.

## Capability state

```text
BEYVRA_OPERATIONS_WRITE=false
BEYVRA_NOTIFICATION_REQUEST=false
BEYVRA_REPORT_REQUEST=false
ODOO_WRITE=false
ENABLE_EXTERNAL_DELIVERY=false
DEAD_LETTER_REPLAY=false
REAL_TRADING_EXECUTION=false
REAL_WALLET_DEPOSITS=false
REAL_WALLET_WITHDRAWALS=false
REAL_WALLET_TRANSFERS=false
PAYMENT_EXECUTION=false
CUSTODY_EXECUTION=false
CHAIN_BROADCAST=false
```

Workflow activation never enables any capability.

## Signed event transport

The existing Beyvra webhook contract already uses stable event IDs and HMAC-SHA256 signatures. The Middleware subscription must be exact, tenant-scoped, private/allowlisted, timestamped and replay-protected. Middleware durably persists the event before acknowledging it.

A provider or delivery timeout produces an unknown result. Middleware reconciles the Beyvra operation or signed-delivery record before any retry. Exact replays return the original result; conflicting payloads using the same idempotency key are rejected.

## Frontend relationship

`appolon1908-hue/beyvra-frontend` is a browser client of this backend only. It does not call n8n or Middleware and never receives an n8n service credential. The backend exposes user-authorized status, safe error, approval and notification projections to the frontend through its canonical REST/realtime contracts.

## Dependencies

```text
N8N governance baseline and control-plane contract
Middleware operation-policy and durable-job contract
Keycloak machine-identity contract
N8N automation/beyvra-operations-v2-20260827
beyvra-frontend integration/automation-status-ui-v2-20260827
```

## Current state

```text
SOURCE_ONLY=YES
DIRECT_N8N_BEYVRA_ACCESS=NO
DIRECT_N8N_FINANCIAL_ACCESS=NO
WORKFLOWS_ACTIVE=NO
FINANCIAL_EFFECTS_ENABLED=NO
LIVE_SERVER_CHANGED=NO
PRODUCTION_DEPLOYED=NO
```

This branch adds a contract only. It does not change a database, route, broker, wallet, payment provider, webhook destination, runtime capability or live deployment.
