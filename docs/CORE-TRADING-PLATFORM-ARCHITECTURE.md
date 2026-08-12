# Core trading platform architecture

Certified design date: 2026-08-11. This is readiness architecture, not provider or production approval.

Browser clients use only `/api/v1/*` and `/ws/v2/`. The application separates Market Data Authority, simulation-first Trading Authority, account/risk policy, and the external Financial Service. Adapters cannot become authoritative merely because credentials exist.

Market data flows `approved adapter -> validation/normalization -> freshness authority -> canonical persistence/outbox -> API/realtime`. A sequence gap marks the stream degraded until an authoritative snapshot is installed. Only one provider is authoritative for a stream unless an explicit consensus policy exists.

Orders flow `authenticated request -> idempotency -> eligibility/risk -> simulation reservation -> simulation execution -> projection/outbox/audit`. The current router returns only `SIMULATION` or `DENIED`; `PAPER` and `LIVE` are denied. Real balances, reservations, and settlement remain Financial Service authority through a scoped client; application database access to that service is prohibited.

External mutation adapters must use idempotency and operation lookup after unknown outcomes. Webhooks require signature verification, timestamp/replay checks, idempotent inbox processing, transactional outbox, and dead-letter handling.

Safety baseline: all real-money, deposit, withdrawal, transfer, trading, external-execution, custody, and payment activation flags are false/disabled. No production change is part of this certification.

