# Beyvra API and webhook inventory

This inventory reflects the staging Django route tree. All authenticated routes require the existing session/JWT authentication; organization-scoped routes additionally resolve `X-Organization-ID` or the caller's authorized membership.

## Identity, registration, recovery and session

| Method | URL | Purpose | Authority/state |
|---|---|---|---|
| GET | `/api/v1/auth/oidc/config/` | Public, non-secret client capability metadata | Returns 503 while the reviewed Keycloak client is disabled |
| GET | `/api/v1/auth/oidc/login/?next=<path>` | Start Authorization Code + PKCE S256 login | Keycloak owns human authentication |
| GET | `/api/v1/auth/oidc/register/?next=<path>` | Start Keycloak self-registration | Keycloak owns registration, terms and verified email |
| GET | `/api/v1/auth/oidc/password-reset/?next=<path>` | Start Keycloak UPDATE_PASSWORD action | Keycloak owns lookup, token and password consumption |
| GET | `/api/v1/auth/oidc/callback/` | Validate state/nonce, exchange code server-side and bind identity | Exact issuer + immutable subject; browser receives no Keycloak token |
| GET | `/api/v1/auth/oidc/csrf/` | Bootstrap the same-origin CSRF token | Public, non-secret response |
| POST | `/api/v1/auth/oidc/logout/` | Revoke Beyvra session and return Keycloak end-session redirect | Requires CSRF and the HttpOnly session |
| POST | `/api/v1/auth/token/refresh/` | Rotate the Beyvra HttpOnly session cookies | No access or refresh token in the response body |
| GET | `/api/v1/session` | Resolve anonymous, guest or registered state | HttpOnly cookie authentication |

When `KEYCLOAK_IDENTITY_ENABLED=true`, `LOCAL_PASSWORD_AUTH_ENABLED` must be false and local login, email-OTP registration, password reset/change and local MFA routes are not registered. Beyvra administrator profile/status operations remain available, but administrator creation, credential reset, role assignment and MFA authority remain in Keycloak. Keycloak roles are synchronized to the local application profile at login.

Successful first binding emits `identity.account.provisioned` through the transactional outbox/NATS boundary. It contains only hashed identity reference, local user reference, role and authority. It is not a synchronous login dependency and no password, OTP, authorization code, verifier or token is allowed in the event.

## Klyrow email and callback boundary

| Direction | Endpoint/transport | Contract |
|---|---|---|
| Beyvra backend → Klyrow | `POST /v1/internal/email/beyvra/send` | OAuth service credential, idempotency key and transactional outbox for ordinary Beyvra mail |
| Keycloak → Klyrow | Private SECURITY SMTP | Password-reset exception; bypasses Beyvra API, Middleware, Odoo and n8n |
| Klyrow → Middleware | `POST /api/v1/klyrow/events` | OIDC bearer + HMAC + event ID/idempotency headers; not a Beyvra backend route |

There is no Beyvra authentication webhook. Source contracts confirm these routes and guards; production delivery, DNS and SMTP remain unconfirmed until the required runtime probes pass.

## Demo trading

| Method | URL | Purpose | Tenant behavior |
|---|---|---|---|
| POST | `/api/v1/demo/sessions` | Idempotent guest Demo session | Assigns the staging Demo tenant |
| GET | `/api/v1/session` | Resolve current session | Returns anonymous/guest/registered state |
| GET | `/api/v1/demo/config` | Server limits/assets/durations | Authenticated Demo configuration |
| POST | `/api/v1/demo/orders` | Submit one simulated order | Wallet and trade must belong to active tenant |
| GET | `/api/v1/demo/trades` | List open/settled Demo trades | Tenant-filtered |
| GET | `/api/v1/demo/wallet` | Available/reserved virtual funds | Tenant-filtered |
| POST | `/api/v1/demo/wallet/refill` | Idempotent Demo reset | Tenant-filtered; preserves history |

## Wallets and transactions

| Method | URL | Purpose |
|---|---|---|
| GET/POST | `/api/wallet/wallets/` | List/create wallets |
| GET/PATCH | `/api/wallet/wallets/<id>/` | Read/update owner wallet |
| GET | `/api/wallet/wallets/<id>/refill/` | Legacy Demo refill endpoint |
| PUT | `/api/wallet/<id>/archive/` | Archive wallet |
| GET | `/api/wallet/transactions/` | Owner transaction history |
| POST | `/api/wallet/wallets/<id>/deposit/` | Legacy funding endpoint; disabled in Demo mode |
| POST | `/api/wallet/wallets/<id>/withdraw/` | Legacy withdrawal endpoint; disabled in Demo mode |
| POST | `/api/wallet/wallets/<id>/transfer/` | Wallet transfer; disabled in Demo mode |

Wallet CRUD and transaction reads are tenant-filtered. Real-money routes remain disabled by `PAPER_TRADING_ONLY`.

## Notifications, preferences and webhooks

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/notification/notifications/` | Notification preferences |
| PUT | `/api/notification/toggle_notification/` | Enable/disable a preference |
| GET/POST | `/api/notification/alerts/` | User price alerts |
| GET | `/api/notification/alerts/<id>/` | Read owned alert |
| GET | `/api/notification/inbox/` | Tenant-scoped notification inbox |
| POST | `/api/notification/inbox/<id>/read/` | Mark event read |
| POST | `/api/notification/inbox/read-all/` | Mark all events read |
| GET/POST | `/api/notification/webhooks/` | Create/list signed webhook subscriptions |
| GET/PATCH/PUT/DELETE | `/api/notification/webhooks/<id>/` | Manage owned subscription |
| GET | `/api/notification/webhooks/<id>/deliveries/` | Delivery history |
| POST | `/api/notification/webhooks/<id>/test/` | Queue a signed test event |
| POST | `/api/notification/webhooks/<id>/retry/` | Retry failed/dead delivery |

Webhook secrets are write-only and encrypted at rest. Delivery payloads are JSON signed with HMAC-SHA256 and include event ID, event category and signature version. Delivery retries are bounded at five attempts; inactive subscriptions become dead-lettered instead of remaining pending.

## Integrations and service webhooks

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/v1/tenant/context` | Active organization context |
| GET/POST | `/api/v1/integrations/crm/connections` | Tenant-scoped CRM connections |
| GET/PATCH | `/api/v1/integrations/crm/connections/<id>` | Manage CRM connection |
| POST | `/api/v1/integrations/crm/<connection_id>/users` | Signed CRM inbound webhook |
| GET/POST | `/api/v1/integrations/service-tokens` | Tenant service-token management |
| POST | `/api/v1/integrations/service-tokens/<id>` | Rotate/revoke service token |

CRM inbound requests require timestamp, event ID and HMAC signature. Replays are rejected and all integration records are tenant-scoped.

## WebSocket routes

| URL | Purpose | Isolation |
|---|---|---|
| `/ws/trades/` | User trade updates | Tenant + user channel |
| `/ws/users/` | User notifications | Tenant + user channel |
| `/ws/market-data/` | Authenticated market feed | Global market data; no user payloads |

## Webhook delivery contract

Outbound deliveries are `POST` requests with a JSON body and these headers:

- `X-Codestra-Event` — event category
- `X-Codestra-Event-Id` — stable event UUID for deduplication
- `X-Codestra-Signature-Version: HMAC-SHA256`
- `X-Codestra-Signature-256: sha256=<hex digest>` — HMAC over the exact request body

Delivery states are pending, failed, succeeded and dead-lettered. Requests are bounded to five attempts, do not follow redirects, and inactive subscriptions are dead-lettered immediately. Test and retry actions enqueue the same signed delivery path; they do not bypass validation.

## Remaining gaps

- No standalone tenant-owned media table/API exists; user profile images remain user-scoped by design.
- The WebSocket unit tests now use tenant-qualified groups; external consumers still need to migrate from legacy unqualified group names before those names can be retired.
- Legacy funding routes remain present for compatibility but are blocked in Demo mode; they should be retired once clients stop calling them.
- API schema generation should be run and published after the next staging release.
