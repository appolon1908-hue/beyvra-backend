# Integrated certification results

```text
POSTGRESQL_VERSION=16
MIGRATION_FROM_ZERO=PASS
MIGRATION_DRIFT=NONE
ROLLBACK=PASS
REAPPLY=PASS
FULL_BACKEND_TEST_COUNT=593
FULL_BACKEND_SUITE=PASS (724.437 seconds)
MYPY=PASS (691 source files)
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_TESTS=PASS (106 tests in 14 files)
FRONTEND_BUILD=PASS
OPENAPI=PASS
DUPLICATE_OPENAPI_KEYS=0
```

The combined run used the exact converged PostgreSQL-backed application tree,
not isolated mission branches. Retired wallet/payment/real-wallet tests were
removed with their writable routes; canonical financial-boundary, simulation,
tenant, idempotency, concurrency, event, API, and realtime tests remain.
