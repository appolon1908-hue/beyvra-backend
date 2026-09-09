# Codestra Beyvra Integration Fabric v2

Beyvra remains authoritative for every account, compliance record, report, subscription, demo/real trading record, wallet, ledger, payment, deposit, withdrawal, transfer, custody operation, broker connection, and provider credential.

The only n8n workflow family is `product.beyvra-nonfinancial`. The runtime path is:

```text
Beyvra frontend -> Beyvra backend -> Kong Beyvra cell -> Middleware
Middleware durable job -> private Beyvra n8n cell
n8n -> Middleware command API -> Beyvra automation-safe adapter -> Beyvra backend
```

The browser never calls n8n or Middleware directly. n8n never calls Beyvra, its database, a broker, payment provider, wallet provider, blockchain, custody system, or third-party provider directly.

## Allowed command prefix

```text
beyvra.operations.
```

Allowed operations are limited to onboarding task coordination, compliance reminders, support escalation, security/operational alerts, report requests/readiness, notification requests, CRM projections, signed-webhook reconciliation, and operation-status reads.

## Prohibited prefixes

```text
trade.
order.
wallet.
ledger.
hold.
payment.
deposit.
withdrawal.
transfer.
custody.
chain.
broker.
provider.
```

A prohibited prefix is rejected before a job is created, even in demo mode. No n8n workflow may make or approve a financial decision.

## Correctness

- Middleware derives tenant and actor from the durable job.
- Every mutation requires an idempotency key and expected resource version where applicable.
- A timeout is `UNKNOWN`; the adapter reconciles before retry.
- Success is returned only after Beyvra read-back.
- High-risk support/security actions require protected approval.
- All capabilities are disabled by default.

No runtime deployment or financial capability is authorized by this source contract.
