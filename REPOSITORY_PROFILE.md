# Repository Profile — `beyvra-backend`

## Identity

- **Repository:** `appolon1908-hue/beyvra-backend`
- **Visibility:** public
- **Default branch:** `main`
- **Category:** product backend — trading and investment platform
- **Primary authority:** Beyvra application APIs, tenant-scoped product workflows, simulation, control evidence, and provider-neutral projections

## Purpose

This repository provides the server-side Beyvra application: identity/session integration, tenant and entitlement decisions, market and instrument projections, simulation orders, positions, portfolio evidence, compliance workflows, notifications, operator controls, audit, reconciliation, and release-safety interfaces.

## Authority boundaries

### This repository owns

- Beyvra application and API contracts
- tenant-scoped authorization and product workflow enforcement
- simulation-only order, execution, position, portfolio, surveillance, post-trade, and valuation state
- provider-neutral intent, status, evidence, and reconciliation projections
- durable idempotency, optimistic concurrency, immutable audit, and outbox/inbox behavior
- fail-closed capability reporting and read-only release certification

### This repository does not own

- browser presentation or client-side financial authority
- Keycloak realm, credential, token, or SMTP authority
- Kong/Caddy edge authority
- Codestra Middleware cross-system delivery authority
- n8n business or financial system-of-record authority
- real monetary balances, ledger finality, custody finality, or settlement finality; those remain Financial Service/provider authorities
- production activation merely because source was merged

## Canonical integrations

- `appolon1908-hue/beyvra-frontend` — browser client
- Keycloak — user and service identity
- Kong/Caddy — governed ingress and routing
- Codestra Middleware — cross-system commands, events, and delivery
- n8n — non-financial orchestration only through Middleware
- Financial Service — real-money and financial-finality authority
- governed market-data, broker, payment, notification, and custody providers

## Required safety posture

```text
REAL_TRADING_ENABLED=false
EXTERNAL_EXECUTION_ENABLED=false
LIVE_BROKER_ROUTING_ENABLED=false
FIX_LIVE_SESSION_ENABLED=false
REAL_MONEY_ENABLED=false
PAYMENTS_ENABLED=false
LIVE_CUSTODY_ENABLED=false
CROSS_CHAIN_TRANSFERS_ENABLED=false
```

These names are the actual runtime gates read by the current backend and read-only release policy. A separate protected activation release is required to change any live-effect capability. Source merge, image build, staging deployment, or read-only production canary does not authorize real trading or money movement.

## Engineering and release rules

1. Use narrow pull requests with exact-head CI and independent review.
2. Keep mutation APIs durably idempotent, versioned, tenant-scoped, and auditable.
3. Preserve one canonical authority per domain; compatibility endpoints must delegate and advertise their successor.
4. Build immutable images from the protected merge SHA, record exact digests, and promote the same digests without rebuilding or retagging.
5. Fail closed on source/digest mismatch, missing identity, stale evidence, provider uncertainty, monitoring loss, or live-effect movement.
6. Keep secrets, private keys, customer data, database dumps, and secret-bearing evidence out of Git.

## Current production posture

The repository contains signed, immutable **read-only** release and rollback machinery. Production readiness still depends on protected merge evidence, environment-owned secrets, exact digest read-back, staging certification, backup/restore proof, monitoring, and a separately approved live-capability activation.

## Related catalog

The broader account-level repository catalog is maintained outside this repository. This file is the local authority profile for `beyvra-backend`.
