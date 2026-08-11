# Compliance inventory

Inventory date: 2026-08-11. Scope: canonical backend and client portal. Financial PostgreSQL and financial service were not accessed or changed.

| Existing control | Location | Classification | Disposition |
|---|---|---|---|
| Canonical compliance dataclass | `FX/apps/compliance/domain.py` | DUPLICATE | Replaced by explicit persisted authorities and policy service. |
| Legacy KYC `verified` boolean/status | `FX/users/models.py`, serializers, admin views | LEGACY / UNSAFE | Compatibility intake only; never eligibility authority. |
| User verification booleans/statuses | `FX/users/models.py` | LEGACY | Authentication/profile concerns only. |
| IP/country lists | `FX/security/*`, middleware | DUPLICATE | Network-security controls; not jurisdiction authority. |
| Paper/live/execution and real-value flags | `FX/FX/settings.py`, real wallet, trading integration | AUTHORITATIVE | Retained fail-closed; all real-value constants remain false. |
| Canonical trading endpoints | `FX/apps/trading/api/*` | AUTHORITATIVE | Server-side eligibility now gates simulation preview/create and snapshots decisions. |
| Legacy trade creation | `FX/trade/*` | LEGACY / UNSAFE | Historical API; not canonical eligibility surface. Release routing must keep it unavailable for real value. |
| Real-wallet tenant compliance profile/restrictions | `FX/real_wallet/models.py`, `compliance.py` | DUPLICATE / UNSAFE | Quarantined behind hard-disabled real-wallet endpoints. It is not customer/account eligibility authority and was not modified because Financial PostgreSQL is out of scope. Any future real-value activation must first migrate this dependency to canonical account-level eligibility. |
| Real-wallet compliance URLs | `FX/real_wallet/urls.py` | LEGACY / AUTHORITATIVE DENY | Continue returning `FEATURE_DISABLED`; they must not shadow or replace canonical safe summary APIs. |
| Provider governance | `FX/provider_governance/*` | AUTHORITATIVE for other providers | Compliance providers have separate disabled-by-default governance. |
| Old KYC screens/hooks | client `api/kyc`, KYC pages | UI_ONLY / LEGACY | Submission UI only; canonical summary comes from compliance APIs. |
| Frontend trading checks | platform chart container | UI_ONLY | Convenience only; server remains authority. |
| AML, sanctions, jurisdiction, restrictions, cases, overrides | no prior persisted authority | MISSING | Implemented by canonical compliance app. |
| Shared transactional outbox | `FX/apps/foundation/models.py`, publisher | AUTHORITATIVE | Compliance mutations enqueue safe private events through the shared outbox; the duplicate compliance-local outbox was removed. |
| Compliance websocket event schemas | no prior schemas | MISSING | Added safe private channel registry contracts and user-scoped event channels. |

Search terms included `is_verified`, KYC, AML, sanctions, compliance, restricted, blocked, approved, rejected, review, risk, country, jurisdiction, and capability booleans across models, routes, admin code, frontend, flags, migrations, and integrations.
