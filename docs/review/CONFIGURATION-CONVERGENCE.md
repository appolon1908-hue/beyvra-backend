# Configuration convergence

## High-risk controls

| Capability | Keys found | Behavior | Status |
|---|---|---|---|
| Real trading | `REAL_TRADING_ENABLED`, `LIVE_TRADING_ENABLED` | canonical setting is fail-closed; duplicate spelling remains | CONFLICT |
| External execution | `EXTERNAL_EXECUTION_ENABLED` | hard false in checked-out backend | PASS |
| Real money | `REAL_MONEY_ENABLED`, real-wallet mutation flags | default/hard false and system checks reject activation | PASS WITH LEGACY FLAGS |
| Financial DB | Financial database URL/alias checks | backend system check rejects direct credentials/alias | PASS |
| Provider endpoints | provider-specific URLs and credential file root | sandbox/live capability is distributed across adapters | REVIEW |

Configuration remains split among Django settings, Compose, CI, frontend environment variables, Centrifugo, NATS bootstrap, and mission branches. High-risk capability flags need one named hierarchy and one evaluator; missing or invalid values must remain false.
