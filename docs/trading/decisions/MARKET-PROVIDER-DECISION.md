# Market provider decision package

| Candidate | Adapter | Capabilities | Classification |
|---|---|---|---|
| Existing configured provider boundary | Yes | Historical candles; quote/status contract; no licensed realtime activation | BOUNDARY_ONLY_CREDENTIALS_REQUIRED |
| Synthetic fixture | Yes | Deterministic contract tests only | ACCEPTABLE_WITH_RESTRICTIONS |

No provider is recommended for activation until the owner supplies an approval
reference, license/redistribution decision, credential reference, supported
symbols/timeframes, and expiry. Public reachability is not approval.
