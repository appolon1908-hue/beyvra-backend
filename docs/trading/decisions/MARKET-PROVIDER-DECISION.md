# Market provider decision package

| Candidate | Adapter | Capabilities | Classification |
|---|---|---|---|
| Binance public REST | Existing historical adapter | Crypto candles | APPROVAL_AND_LICENSE_REVIEW_REQUIRED |
| Twelve Data | Existing historical adapter | Equity, FX, and crypto candles; credential required | APPROVAL_LICENSE_AND_CREDENTIAL_REQUIRED |
| Synthetic fixture | Yes | Deterministic contract tests only | ACCEPTABLE_WITH_RESTRICTIONS |

No provider is recommended for activation until the owner supplies an approval
reference, license/redistribution decision, credential reference, supported
symbols/timeframes, and expiry. Public reachability is not approval.

Runtime activation is fail-closed. `MARKET_PROVIDER_ENABLED=true` is
insufficient by itself: approval, license, and protected credential references
must all be non-empty. No candidate is selected or activated by this record.
