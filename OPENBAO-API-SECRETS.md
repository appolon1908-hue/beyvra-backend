# OpenBao API secret integration

Source authority: [Codestra-OpenBao](https://github.com/appolon1908-hue/Codestra-OpenBao).
The machine-readable contract is `openbao-secret-consumer.v1.json`.
This change prepares file-based credential consumption; runtime binding is unverified.

For each admitted process, render its bundle in Codestra-OpenBao using
`scripts/render_application_secrets.py`. The default selection contains required
startup bindings; add `--include SETTING_NAME` only for an enabled integration.
Run the agent as the same non-root UID/GID as its consumer. Use private directories
on a memory-backed volume and read-only mounts in the application container.
The agent writes mode 0400, with no backup copy or token sink. Consumers accept
0400 or 0600 private regular files owned by the runtime user; links, directories,
pipes, empty/oversized/invalid files and conflicting inline credentials are rejected.
Remove the matching inline environment setting when supplying its `_FILE` setting.
A configured file failing to load stops configuration; it never falls back to an
inline value. Local development without a file retains existing configuration behavior.

The agent reads KV-v2 records with a string `payload` field. The logical namespace
below maps to `/v1/codestra/data/<environment>/...` in the private native API.
No provider credentials belong in browser variables, images, Git or logs.
OpenBao bootstrap/unseal keys and user/customer records are outside this contract.

Settings are loaded at process startup. After Agent renders a rotated value,
restart the affected consumer under the rollout supervisor, verify provider access,
and revoke the old credential only after successful cutover. Static KV refresh is
not provider-key rotation. A reader observing a new file does not prove that an
already-running SDK client has reloaded it. Never dump settings or error `.errors()`
payloads; Pydantic error formatting and secret-field repr are redacted here, but
application-specific diagnostic serialization still requires care.

## Separate Beyvra workloads

`beyvra-api` receives only application identity, database, cache and notification
configuration. `beyvra-market-data`, `beyvra-funding`, and
`beyvra-trading-executor` each have a separate policy. They must be bound to
separately admitted processes/adapters. The existing monolith does not establish
that isolation; do not mount all four bundles into the web API. Broker entitlements,
read-only versus trading permissions, funding authorization and live account
certification remain independent release requirements. This change preserves
`PAPER_TRADING_ONLY = True` and does not turn on financial effects.

Password-reset tokens continue to use Django's established `SECRET_KEY` token
signing path. `PASSWORD_RESET_SIGNING_KEY_FILE` is not part of this OpenBao
consumer contract until a separately reviewed token generator consumes it.

## beyvra-api

Logical prefix: `codestra/<environment>/beyvra/api/runtime/`.

| Setting | File reference | Startup required |
| --- | --- | --- |
| `SECRET_KEY` | `SECRET_KEY_FILE` | Yes |
| `DB_PASSWORD` | `DB_PASSWORD_FILE` | Yes |
| `REDIS_PASSWORD` | `REDIS_PASSWORD_FILE` | Yes |
| `EMAIL_OTP_PEPPER` | `EMAIL_OTP_PEPPER_FILE` | When integration requires it |
| `GOOGLE_OIDC_CLIENT_SECRET` | `GOOGLE_OIDC_CLIENT_SECRET_FILE` | When integration requires it |
| `COMPLIANCE_WEBHOOK_SECRET` | `COMPLIANCE_WEBHOOK_SECRET_FILE` | When integration requires it |
| `EMAIL_HOST_PASSWORD` | `EMAIL_HOST_PASSWORD_FILE` | When integration requires it |
| `TWILIO_AUTH_TOKEN` | `TWILIO_AUTH_TOKEN_FILE` | When integration requires it |
| `BEYVRA_EMAIL_CLIENT_SECRET` | `BEYVRA_EMAIL_CLIENT_SECRET_FILE` | When integration requires it |
| `DATA_ENCRYPTION_KEY` | `DATA_ENCRYPTION_KEY_FILE` | When integration requires it |
| `API_TOKEN_PEPPER` | `API_TOKEN_PEPPER_FILE` | When integration requires it |
| `WEBHOOK_MASTER_KEY` | `WEBHOOK_MASTER_KEY_FILE` | When integration requires it |

## beyvra-trading-executor

Logical prefix: `codestra/<environment>/beyvra/execution/provider/`.

| Setting | File reference | Startup required |
| --- | --- | --- |
| `API_KEY_ALPACA` | `API_KEY_ALPACA_FILE` | Yes |
| `API_SECRET_ALPACA` | `API_SECRET_ALPACA_FILE` | Yes |

## beyvra-market-data

Logical prefix: `codestra/<environment>/beyvra/market-data/providers/`.

| Setting | File reference | Startup required |
| --- | --- | --- |
| `TWELVE_DATA_API_KEY` | `TWELVE_DATA_API_KEY_FILE` | When integration requires it |
| `SCHEMA_API_KEY` | `SCHEMA_API_KEY_FILE` | When integration requires it |
| `FIXER_API_KEY` | `FIXER_API_KEY_FILE` | When integration requires it |
| `NEWSDATA_API_KEY` | `NEWSDATA_API_KEY_FILE` | When integration requires it |
| `NEWS_DATA_API_KEY` | `NEWS_DATA_API_KEY_FILE` | When integration requires it |
| `POLYGON_API_KEY` | `POLYGON_API_KEY_FILE` | When integration requires it |
| `COINGECKO_API_KEY` | `COINGECKO_API_KEY_FILE` | When integration requires it |

## beyvra-funding

Logical prefix: `codestra/<environment>/beyvra/funding/providers/`.

| Setting | File reference | Startup required |
| --- | --- | --- |
| `STRIPE_SECRET_KEY` | `STRIPE_SECRET_KEY_FILE` | When integration requires it |
| `STRIPE_ENDPOINT_SECRET` | `STRIPE_ENDPOINT_SECRET_FILE` | When integration requires it |
