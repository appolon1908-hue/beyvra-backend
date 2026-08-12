# API inventory

The runtime schema is generated at `contracts/openapi/beyvra-v1.yaml` and validated by `scripts/validate_openapi.py`, whose YAML loader rejects duplicate mapping keys.

```text
CANONICAL_PREFIX=/api/v1/
CANONICAL_REALTIME_PATH=/ws/v2/
OPENAPI_PATHS=535
OPENAPI_OPERATIONS=654
DUPLICATE_EXACT_ROUTE_PATTERNS=0
DUPLICATE_OPENAPI_KEYS=0
LEGACY_PREFIXES=/api/user/;/api/trades/
LEGACY_CLASSIFICATION=DEPRECATED_COMPATIBILITY_READ_OR_FAIL_CLOSED
OPENAPI_SHA256=d602beef-a949-441e-79b4-41357c860cf5-59b82d07-af10-5e8d-40e67f6caf8a140
```

Real-value wallet, deposit, withdrawal, and transfer paths are Financial Service boundary adapters and remain fail closed. Application-owned legacy wallet/payment and real-wallet routes are removed.
