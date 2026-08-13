# Architecture Convergence Conflict Register

Each item retains the required audit fields. Status values are `OPEN`, `IN_PROGRESS`, `RESOLVED`, or `BLOCKED`.

## AC-001 — Distributed mission branches

```text
ID=AC-001
SEVERITY=P0
DOMAIN=INTEGRATION
FILES=repository branch graph
CANONICAL_OWNER=feat/beyvra-architecture-convergence
CONFLICTING_IMPLEMENTATIONS=independent backend architecture mission branches
RESOLUTION=selectively integrate shared stacks and manually reconcile sibling authorities
TEST=combined candidate certification
STATUS=RESOLVED
```

## AC-002 — Financial state authority

```text
ID=AC-002
SEVERITY=P0
DOMAIN=FINANCIAL_BOUNDARY
FILES=FX/wallet; FX/payments; FX/trade/demo_engine.py; FX/real_wallet
CANONICAL_OWNER=FINANCIAL_SERVICE for real value; application simulation/read models otherwise
CONFLICTING_IMPLEMENTATIONS=legacy wallet/payment mutations and Financial Service boundary
RESOLUTION=classify mutations and fail closed for real financial effects
TEST=financial boundary tests and direct-access scan
STATUS=RESOLVED
```

## AC-003 — Settlement authority

```text
ID=AC-003
SEVERITY=P0
DOMAIN=SETTLEMENT
FILES=FX/apps/trading; post-trade branch; FX/real_wallet
CANONICAL_OWNER=FINANCIAL_SERVICE for monetary finality; application backend for workflow intent/projection
CONFLICTING_IMPLEMENTATIONS=backend settlement workflow models versus monetary settlement semantics
RESOLUTION=make backend records provider-neutral workflow intent/projection only
TEST=post-trade and Financial Service boundary tests
STATUS=RESOLVED
```

## AC-004 — Duplicate trading models and migrations

```text
ID=AC-004
SEVERITY=P0
DOMAIN=TRADING_AND_MIGRATIONS
FILES=FX/apps/trading; FX/trade; FX/portfolio; migrations
CANONICAL_OWNER=APPLICATION_BACKEND apps.trading aggregate/projections
CONFLICTING_IMPLEMENTATIONS=legacy and mission order, execution, fill, trade, position, reservation, settlement models
RESOLUTION=combine desired Django state, adapt legacy models, then converge migration graph
TEST=PostgreSQL 16 zero/existing/rollback/reapply and model authority scans
STATUS=RESOLVED
```

## AC-005 — Event topology and delivery

```text
ID=AC-005
SEVERITY=P0
DOMAIN=EVENTS_OUTBOX_INBOX
FILES=publisher; JetStream bootstrap; consumers; outbox/inbox implementations
CANONICAL_OWNER=domain-prefixed event registry and transactional domain outbox pattern
CONFLICTING_IMPLEMENTATIONS=application.* publisher and market/news/private/system stream coverage; duplicate outboxes
RESOLUTION=one subject topology with complete stream coverage and idempotent consumers
TEST=subject coverage, transaction, retry, and deduplication tests
STATUS=RESOLVED
```

## AC-006 — Realtime contract and channel dialect

```text
ID=AC-006
SEVERITY=P0
DOMAIN=REALTIME
FILES=Nginx; Centrifugo; backend publishers; frontend UnifiedRealtimeClient
CANONICAL_OWNER=/ws/v2/ and REALTIME-CHANNEL-REGISTRY.md
CONFLICTING_IMPLEMENTATIONS=/connection/websocket; colon/dotted/compat market channels; duplicate sequence tracking
RESOLUTION=publish and consume one V2 registry through the public proxy path
TEST=backend/frontend contract, reconnect, dedup, gap-recovery, and unknown-subscription tests
STATUS=RESOLVED
```

## AC-007 — API, OpenAPI, and error contracts

```text
ID=AC-007
SEVERITY=P0
DOMAIN=API_CONTRACT
FILES=FX/FX/urls.py; domain URLs/views; contracts/openapi; frontend API clients
CANONICAL_OWNER=integrated runtime-generated versioned API contract
CONFLICTING_IMPLEMENTATIONS=duplicate legacy/versioned writes, duplicate YAML keys, divergent error envelopes
RESOLUTION=classify routes, remove duplicate writable authority, generate/validate one contract and error envelope
TEST=route inventory, duplicate-key parser, schema drift, and frontend parity
STATUS=RESOLVED
```

## AC-008 — Position and P&L authority

```text
ID=AC-008
SEVERITY=P1
DOMAIN=POSITION_VALUATION
FILES=FX/portfolio; FX/trade; valuation branch; frontend calculations
CANONICAL_OWNER=backend executed-trade position projection and valuation read model
CONFLICTING_IMPLEMENTATIONS=legacy portfolio/trade/frontend calculations
RESOLUTION=adapt or deprecate parallel calculators
TEST=full simulated lifecycle and reconciliation tests
STATUS=RESOLVED
```

## AC-009 — Configuration, URLs, and infrastructure

```text
ID=AC-009
SEVERITY=P1
DOMAIN=RUNTIME_CONFIGURATION
FILES=FX/FX/settings.py; FX/FX/urls.py; Dockerfile; docker-compose*; nginx*; workflows; entrypoints
CANONICAL_OWNER=integrated runtime composition
CONFLICTING_IMPLEMENTATIONS=mission-specific settings, URL, and infrastructure patches
RESOLUTION=modular composition with unique settings/routes and one health/realtime topology
TEST=settings/URL system checks, Compose validation, and CI gates
STATUS=RESOLVED
```

## AC-010 — Backup artifacts and legacy cleanup

```text
ID=AC-010
SEVERITY=P1
DOMAIN=REPOSITORY_HYGIENE
FILES=backups/; legacy modules and compatibility paths
CANONICAL_OWNER=external authorized backup storage and deprecation register
CONFLICTING_IMPLEMENTATIONS=mutable backup artifacts in worktree and unclassified dead code
RESOLUTION=verify preservation, remove worktree copies, ignore backups, and remove only consumer-free legacy code
TEST=artifact scan and no-consumer/no-import migration checks
STATUS=RESOLVED
```
