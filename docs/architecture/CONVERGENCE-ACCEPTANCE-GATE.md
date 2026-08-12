# Whole-platform convergence acceptance gate

## Disposition of PR #46

Backend PR #46 is an audit and evidence input. It MUST NOT be merged or represented as certified architecture. The convergence implementation must proceed on a dedicated branch and may claim certification only after every blocking gate below is supported by reproducible evidence from the integrated candidate.

Passing isolated repository tests does not override a failed architecture, authority, migration, event, API, realtime, or safety gate.

## Blocking gates

```text
AMBIGUOUS_CANONICAL_AUTHORITIES=0
APPLICATION_SHADOW_REAL_LEDGER=NO

DUPLICATE_WRITABLE_ORDER_MODELS=0
DUPLICATE_WRITABLE_EXECUTION_MODELS=0
DUPLICATE_WRITABLE_FILL_MODELS=0
DUPLICATE_WRITABLE_TRADE_MODELS=0
DUPLICATE_WRITABLE_POSITION_MODELS=0

CONFLICTING_STATE_MACHINES=0

MIGRATION_GRAPH_CONFLICTS=0
MIGRATION_FROM_ZERO=PASS
MIGRATION_DRIFT=NONE
REAPPLY=PASS

PUBLISHED_SUBJECTS_WITHOUT_STREAM=0
UNIDEMPOTENT_REDELIVERABLE_CONSUMERS=0
OUTBOX_TRANSACTION_GAPS=0
INBOX_DEDUP_GAPS=0

REALTIME_CHANNEL_DIALECTS_CANONICAL=1
REALTIME_SCHEMA_CONFLICTS=0
FRONTEND_UNKNOWN_V2_SUBSCRIPTIONS=0

DUPLICATE_WRITABLE_API_AUTHORITIES=0
DUPLICATE_OPENAPI_KEYS=0
OPENAPI=PASS
OPENAPI_DRIFT=NONE

ERROR_CONTRACT_VARIANTS=1
RAW_INTERNAL_ERROR_EXPOSURE_PATHS=0

DUPLICATE_HIGH_RISK_FEATURE_FLAGS=0
KILL_SWITCH_BYPASS_PATHS=0

FULL_BACKEND_SUITE=PASS
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_TESTS=PASS
FRONTEND_BUILD=PASS

SECRET_SCAN=PASS_CURRENT_SOURCE
DEPENDENCY_SCAN=PASS
CONTAINER_SCAN=PASS
SBOM=PASS

REAL_TRADING_ENABLED=false
EXTERNAL_EXECUTION_ENABLED=false
REAL_SETTLEMENT_ENABLED=false
REAL_MONEY_ENABLED=false

REAL_FINANCIAL_EFFECTS=0
PRODUCTION_CHANGED=NO
```

Every zero-valued conflict gate requires an inventory and negative evidence, not merely absence of a failing test. `OPENAPI_DRIFT=NONE` and the frontend parity gates must be measured against artifacts generated from the same integrated SHA.

## Tracked non-blocking follow-up workstreams

These items do not block the core convergence branch, but remain mandatory owner-side work before the applicable external approval:

1. The 18 historical secret candidates (17 backend and one frontend) require repository/provider-owner validation and, where genuine, revocation or rotation plus an approved history-remediation decision. Current-source scanning remains a blocking gate.
2. Governance must be repinned to the exact eventual Financial Service candidate SHA before independent approval. A fail-closed `wrong head` result is expected until that candidate is frozen and repinned by authorized owners.

Neither follow-up may be silently closed, treated as passed, or used to weaken the blocking gates.
