# Beyvra PAPER/LIVE API design notes

## Provenance and implementation status

This document reconstructs the design from the user's revised written 2026 mission
received on 2026-09-12. The named original OpenAPI, AsyncAPI and design-notes files
were not available in either repository or the workspace. This is not an uploaded
original. Reconcile it against any original subsequently provided.

The design describes the target platform. A contract declaration is not evidence
that its implementation, provider adapter, authorization or production activation
is complete. The generated API implementation matrix must distinguish verified
implementation from missing evidence. Final certification must reject every
unresolved operation and every unsupported implementation claim.

## Account authority

`TradingAccount.execution_mode` is either `PAPER` or `LIVE`. The account, never a
browser header or an AI proposal, determines the execution route. Account identity,
tenant, owner, execution mode, base currency and projection binding are immutable.
A PAPER account cannot be converted to LIVE; LIVE has a separate application and
approval lifecycle with identity, security, compliance and product eligibility.

Customer account creation accepts PAPER only. PAPER reset and administrative
simulation adjustment/reset are account-scoped commands. They never post real
journal entries. PAPER cannot deposit, withdraw, transfer real funds, withdraw
crypto or route an external execution. Reject with `ACCOUNT_MODE_NOT_ELIGIBLE`.

Account state is PENDING, ACTIVE, RESTRICTED, SUSPENDED or CLOSED. Trading, funding
and withdrawal permissions are independent and server-enforced. Default-off LIVE
identity is not production approval. PAPER funds remain in their own projection;
LIVE balances derive from the append-only double-entry ledger.

## One contract per responsibility

Customer HTTP: `/api/v1/*`. Workforce HTTP: `/api/admin/v1/*`. Signed service and
provider ingress: `/api/internal/v1/*`. Customer and authorized workforce realtime:
`/ws/v2`. Infrastructure exceptions are health, metrics and schema endpoints.

Orders, executions, positions, portfolio and realtime are shared across account
modes. There is no Demo namespace or Demo OpenAPI tag. Fixed-Time products, if
retained, require an independent product model; their duration and outcome rules
must not be copied into spot-order semantics.

Market data lives under `/api/v1/market-data/*`. Instruments have stable backend
IDs and explicit provider-symbol mappings; clients never guess instrument IDs.
Chart layouts/templates are customer persistence, separate from historical market
candles. News and economic events use normalized provider-neutral resources.

Legacy APIs remain only for measured migration of actual callers. Migrating an
application caller and migrating an operational/E2E caller are both required
before retiring a route in a deployed workload. Existing Financial Service
boundaries remain in force during funding migration.

## Command and response rules

Side-effecting trading, financial and governed admin commands require
`Idempotency-Key`. Scope includes actor, tenant, method and operation; persist the
request hash, correlation ID, status, result and expiry. Same key/body replays the
original result. Different body conflicts with 409. An in-flight result is not a
successful completed response. Preview does not reserve or settle funds.

Cookie-authenticated unsafe HTTP methods require CSRF validation. Authentication
uses OIDC Authorization Code with PKCE S256, server-held provider credentials and
HttpOnly browser session cookies. Customer and workforce authorization are separate
boundaries. Every resource lookup and private subscription enforces tenant and
ownership/role scope, including when supplied IDs are otherwise valid.

Identifiers are opaque strings. Monetary values, prices, quantities and financial
ratios requiring exact arithmetic are decimal strings at the HTTP boundary and
Decimal/NUMERIC internally. Do not use JSON floating-point amounts for ledger or
settlement authority. Timestamps use RFC3339 UTC. Pagination and error-envelope
migration must preserve stable machine codes, request IDs and correlation IDs.

Risk failures use deterministic codes including KYC_REQUIRED, MARKET_CLOSED,
PRICE_STALE, INSUFFICIENT_FUNDS, INSUFFICIENT_MARGIN, PRODUCT_NOT_ALLOWED,
MAX_POSITION_EXCEEDED, MAX_DAILY_LOSS_EXCEEDED, ACCOUNT_RESTRICTED and
TRADING_HALTED. Unavailable implemented features return FEATURE_DISABLED with an
explicit unavailable capability; do not represent an unimplemented adapter as
implemented merely by returning that error.

## Financial and trading truth

Each completed journal balances debits and credits per asset. Entries and executions
are immutable. Holds, reservations, releases, settlement, adjustments and reversals
are commands/events, not direct balance updates. An OMS transition is an immutable
event. IDs for client orders, Beyvra orders, provider orders and executions remain
separate. A button click or provider acknowledgement is not a fill.

Four-eyes approval requires requester and approver to differ, including for platform
administrators. Approval alone does not settle a financial action: execution,
idempotency, audit and reconciliation must also succeed. The approved action and
request hash must match the action executed. Reconciliation measures external vs
internal truth and records breaks; monitoring never repairs business state directly.

## Providers and secrets

Adapters implement provider-neutral market data, news, calendar, execution,
payment-rail, custody, KYC, AML, sanctions and blockchain-risk contracts. Implemented
approved providers activate through OpenBao credentials, configuration, redeploy and
health verification. Connectivity does not bypass product, compliance, risk,
reconciliation, certification or production activation gates.

Only provider workloads receive their scoped secret files. File/inline conflicts,
missing or empty files, symlinks and unsafe permissions fail closed. Never expose
provider credentials in browser configuration/storage, images, source, exceptions,
logs, OpenAPI, health payloads or metric labels. Stripe's publishable key is a
specific allowed public value, not an exemption for other credentials. Django must
not hold seed phrases or raw custody signing keys.

Webhook adapters verify their approved provider's signature, timestamp, event ID,
replay window, amount/asset and account mapping before idempotent inbox processing.
Provider acknowledgement, journal posting and customer notification are separately
tracked outcomes. Provider outage must not collapse unrelated platform domains.

## Realtime, AI, communications and operations

Authorize each private stream server-side. Sequence numbers are monotonic per
stream. On a gap, suspend assumptions, obtain an authorized REST snapshot and
resume at a consistent cursor. Account IDs distinguish PAPER/LIVE streams; there
is no second Demo transport. Admin approvals/incidents require workforce roles.

AI is advisory: approved data → structured proposal → deterministic validation →
order preview → explicit customer confirmation → OMS. It cannot post journals,
approve withdrawals, grant administrators or directly invoke a broker.

Notifications use an outbox and Middleware as the controlled integration plane.
Klyrow delivers email; Telnexa delivers SMS. Delivery callbacks are authenticated,
idempotent and auditable. Provider outages are retried with bounded backoff.

Telemetry flows through OpenTelemetry/Alloy to Prometheus, Loki and Tempo, with
Grafana for visualization and Alertmanager routed through Middleware. Exporters
and monitoring are read-only for business state. Superset is business analytics;
OpenBao is secret authority. Production certification records the exact source SHA,
image digests, tests, migration and recovery evidence. Passing certification never
implicitly enables financial or external execution effects.
