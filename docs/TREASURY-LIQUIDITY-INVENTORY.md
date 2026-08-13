# Treasury and Liquidity Inventory

Candidate: `feat/treasury-liquidity-authority`, starting SHA `d9fd2faabb5cccfa929c3e2acac8fedb61975ad2`.

## Existing authorities

| Capability | Existing source | Classification | Treasury use |
|---|---|---|---|
| Tenant and membership | `integrations.Organization`, `OrganizationMembership` | AUTHORITATIVE | Tenant and role scope |
| Event outbox/inbox | `apps.foundation` | AUTHORITATIVE | Transactional publication and deduplication |
| Audit | `ApplicationAuditEvent` plus PostgreSQL immutability trigger | AUTHORITATIVE | Append-only evidence |
| Financial Service client | `financial_client` | FINANCIAL_SERVICE_DELEGATED | Not invoked by this mission |
| Demo ledger | `integrations.DemoLedgerEntry` | SIMULATION_ONLY | Not treated as treasury ledger |
| Settlement/risk/collateral references | trading/operations modules | READ_MODEL | Inputs only; formulas remain with their owners |
| Treasury models/services/API | None before this branch | MISSING | Implemented in isolated `treasury` app |

Searches covered treasury, liquidity, cash, funding, collateral, encumbrance, margin, settlement, intraday, buffers, sweeps, bank/custody/broker accounts, credit, loans, borrowing, and netting. No application Financial PostgreSQL alias, credential, or direct SQL path was found. Legacy wallet/payment models are not reused as real treasury authority.

## Classification rule

All new positions are projections, fixtures, or simulations. Provider identifiers are mappings only. No live transfer endpoint, real balance ingestion, bank client, custody transfer client, credit facility, or ledger write exists.
