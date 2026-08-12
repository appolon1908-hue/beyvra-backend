# API inventory

The runtime schema is generated at `contracts/openapi/beyvra-v1.yaml` and validated by `scripts/validate_openapi.py`, whose YAML loader rejects duplicate mapping keys.

```text
CANONICAL_PREFIX=/api/v1/
CANONICAL_REALTIME_PATH=/ws/v2/
RUNTIME_API_ROUTE_PATTERNS=616
DUPLICATE_EXACT_ROUTE_PATTERNS=0
DUPLICATE_OPENAPI_KEYS=0
LEGACY_PREFIXES=/api/user/;/api/wallet/;/api/payment/;/api/trades/
LEGACY_CLASSIFICATION=DEPRECATED_COMPATIBILITY_READ_OR_FAIL_CLOSED
OPENAPI_SHA256=9211cc7df0da8dde4192f28f606d2a7e0816267e4386815c9e1646b50c03d30f
```

Real-value wallet, deposit, withdrawal, and transfer paths are Financial Service boundary adapters and remain fail closed. Legacy real-wallet paths are explicitly namespaced under `/api/v1/legacy-real-wallet/`.
