# Beyvra public identity migration inventory

Snapshot date: 2026-08-07. Target production identity: `beyvra.com`.
This is a source/configuration migration only. DNS, certificates, routing,
OAuth-console configuration, monitoring targets, redirects, staging, and
production were not changed.

## Classification

| Match family | Classification | Action |
|---|---|---|
| `staging.codestra.cloud` in Compose, Centrifugo, probes, and active realtime operations documentation | `STAGING_DOMAIN` | Changed to `staging.beyvra.com`; deployment remains separately gated. |
| `tradx.io`, `xtradx.com`, Tradx/Tradex in serializer defaults, SMS, and email templates | `PUBLIC_DOMAIN` / `USER_VISIBLE_BRAND` | Changed to `beyvra.com` and Beyvra; remote legacy logo references were removed. |
| Email subjects, bodies, account notifications, webhook test copy, and OpenAPI titles containing Codestra | `USER_VISIBLE_BRAND` | Changed to Beyvra. |
| `PUBLIC_SITE_URL`, `PUBLIC_API_URL`, `PUBLIC_WS_URL`, `PUBLIC_STATUS_URL`, OAuth callback, CORS, CSRF, hosts, cookie-domain examples | `PRODUCTION_DOMAIN` | Added explicit Beyvra configuration. Realtime uses the certified API hostname rather than inventing an unverified `ws` hostname. Cookies remain host-only by default. No runtime deployment performed. |
| Nginx `server_name` and Centrifugo allowed origin | `PUBLIC_DOMAIN` | Made explicit/configurable for Beyvra; no certificate or listener cutover performed. |
| `X-Codestra-*` webhook/proxy headers | `INTERNAL_NAME` / compatibility protocol | Preserved to avoid silently breaking signed webhook and proxy contracts. Rename requires a versioned dual-header migration. |
| `codestra_*` Prometheus/StatsD metrics, logger names, NATS durable/source names | `INTERNAL_NAME` | Preserved so dashboards, alerts, deduplication, and operational continuity do not break. |
| `codestra_guest_session` cookie | `INTERNAL_NAME` / compatibility state | Preserved to avoid invalidating active demo sessions during a source-only migration. |
| `/run/secrets/codestra`, `/etc/codestra`, Docker network/project names, CI database names | `INTERNAL_NAME` | Preserved; these are not public identity. |
| OpenAPI filenames containing `codestra-*` | `INTERNAL_NAME` / compatibility artifact path | Preserved so tooling and review links remain stable; document titles now say Beyvra. |
| Existing backup paths, rollback image tags, dated audit reports, and previous certification evidence | `HISTORICAL_DO_NOT_CHANGE` | Preserved as immutable operational history. |
| Existing organization row name `Codestra staging` | `HISTORICAL_DO_NOT_CHANGE` | Preserved to prevent creation of a second tenant identity. A separately approved data migration may rename it later. |
| Legacy `/api/bank_account/tradxio/` route | `HISTORICAL_DO_NOT_CHANGE` / `REMOVE_AFTER_MIGRATION` | Preserved because renaming it would add another route and break callers; it remains classified for removal in the API inventory. |

The initial scoped search returned 173 Codestra/domain matches. Every family is
covered above. `scripts/check_public_identity.py` guards active public surfaces
against reintroducing the old domains or Tradx/Tradex identity.

## Cutover prerequisites

Before any environment uses the new public endpoints, independently verify:

1. DNS ownership and records for `beyvra.com`, `www`, `api`, `admin`,
   `platform`, and the intended staging hostname. A dedicated `ws` or `status`
   hostname must not be used until it is independently created and certified.
2. TLS/ACME certificate issuance and renewal.
3. Edge routing, Nginx host matching, WebSocket upgrades, and Centrifugo origin
   authorization.
4. Django hosts, CORS, CSRF, cookie scope, CSP, and secure-cookie behavior.
5. Google OAuth console redirect URIs and every other external callback owner.
6. Email link generation, password reset, invitations, payment callbacks, and
   webhook documentation.
7. Monitoring/alert links and health probes from the approved environment.
8. An approved redirect and rollback plan for old public URLs.

Until those gates pass, `PRODUCTION_CHANGED=NO` and no old-domain redirect is
authorized.

## Repository coverage

This backend repository contains no frontend application environment, PWA
manifest, canonical-page metadata, `robots.txt`, `sitemap.xml`, public TLS/ACME
automation, or production DNS definitions. Those items must be certified in
their owning repositories/infrastructure. Payment and webhook callback URLs are
caller/provider-owned contracts; only safe Beyvra defaults and documentation
were changed here. No provider console or callback registration was mutated.
