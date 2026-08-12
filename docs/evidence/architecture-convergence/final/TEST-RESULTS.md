# Integrated certification results

```text
POSTGRESQL_VERSION=16
MIGRATION_FROM_ZERO=PASS
MIGRATION_DRIFT=NONE
ROLLBACK=PASS
REAPPLY=PASS
FULL_BACKEND_TEST_COUNT=655
FULL_BACKEND_SUITE=PASS (753.207 seconds)
POST_COMMIT_NEWS_TEST_COUNT=42
POST_COMMIT_NEWS_TESTS=PASS
MYPY=PASS (691 source files)
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_TESTS=PASS (67 focused realtime/chart tests)
FRONTEND_BUILD=PASS
OPENAPI=PASS
DUPLICATE_OPENAPI_KEYS=0
```

The combined run used the final converged PostgreSQL-backed application model,
not isolated mission branches. The only source edit after that run was a
type-inference-safe local variable rename in the NewsData normalizer; its full
42-test application suite was rerun successfully against the rebuilt image.
