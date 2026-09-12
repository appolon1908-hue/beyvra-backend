# Beyvra PAPER/LIVE master build

## Authority and sequencing

The revised 2026 mission supersedes the earlier separate Demo/Live design.
Customer orders, executions, positions, portfolio and realtime must share one
contract. The account selects PAPER or LIVE execution. PAPER funds must never
enter the real ledger. Credentials do not grant production activation.

Execute backend B00–B19, frontend F00–F15, final cleanup, then integrated
certification. Each milestone requires its own tested branch, push, PR, required
green checks, independent review, merge and main synchronization. Do not advance
past an unfinished milestone or bypass branch protection.

## B00: in progress, not merge-ready

Baseline audited on 2026-09-12:

- Backend main: `688d6b1`.
- Frontend main: `46472a1e780f20c531297c74b1ab603156abea93`.
- No repository `AGENTS.md` was found in either fresh checkout.
- The requested `beyvra-openapi-3.1.yaml`, `beyvra-asyncapi-3.0.yaml`, and
  `beyvra-api-design-notes.md` were not found in either checkout or the workspace.
  Their location has been requested. Existing contracts are audit inputs, not
  assumed substitutes for the missing authoritative files.

### Existing contract inventory

Counts are HTTP operations, not path items; generated evidence snapshots are
excluded. These counts do not establish implementation completeness.

| Contract in `contracts/openapi/` | Operations | Missing operation IDs |
| --- | ---: | ---: |
| `beyvra-v1.yaml` | 671 | 0 |
| `codestra-demo-v1.yaml` | 240 | 0 |
| `beyvra-treasury-v1.yaml` | 37 | 37 |
| `beyvra-enterprise-experience-v1.yaml` | 26 | 0 |
| `codestra-real-wallet-v1.yaml` | 14 | 0 |
| `beyvra-workspace-v1.yaml` | 8 | 0 |

The current validator discovers eight documents, including the Financial
Service and platform-operations contracts. Validation now rejects duplicate
operation IDs, broken local references, invalid operation shapes, and duplicate
YAML keys. It does not claim full OpenAPI semantic validation or that an endpoint
is implemented. Existing missing IDs remain migration work. External references
fail explicitly rather than being silently accepted or fetched over the network.

The first CI run rejected a modification to the integrity-protected `ci.yml`.
That workflow has been restored. New tests and lint checks run in the separate
read-only `api-contract-validation.yml`; no workflow trust pins, branch rules,
or production controls were relaxed. The repository orchestrator validator and
its release-intent self-tests pass locally with this configuration.

### Runtime and caller findings

| Existing surface | Revised disposition | Evidence / dependency |
| --- | --- | --- |
| `/api/v1/demo/sessions` | REMOVE after caller migration | `FX/FX/urls.py`; frontend `codestraAuthApi.guestDemo` is called from `SignInForm.tsx`. Guest identity creation is not equivalent to authenticated PAPER account creation. |
| `/api/v1/demo/config` | REMOVE after caller migration | `FX/FX/urls.py`; frontend generated client, endpoint registry, and `useDemoConfig.ts` reference the route. Fixed-Time settings must not silently become spot-order rules. |
| Other `/api/v1/demo/*` paths | REMOVE stale contract entries | The old Demo contract advertises paths already absent from runtime; `trade/test_demo_event_producer.py` asserts four removals. |
| `/api/v1/trading/*` | COMPATIBILITY during migration | Existing simulation order service is in `apps.trading.application.simulation`; the new contract requires `/orders`, `/positions`, `/executions`, and `/accounts`. |
| `/api/payment/**` | REMOVE after funding and frontend migration | Preserve the existing Financial Service boundary; do not enable old Stripe/Binance mutations. |
| `/api/v1/market/*` | COMPATIBILITY during migration | Revised authority is `/api/v1/market-data/*`; reconcile the older consolidation inventory when successors are working. |

`SimulatedAccount` currently owns virtual balance projections; it is not the
requested unified `TradingAccount`. Orders and events still use simulation flags
and `SIMULATION` values. A textual DEMO-to-PAPER replacement cannot establish
account ownership, isolation, creation eligibility, or internal routing.

### Remaining B00 work

1. Obtain and inspect the three authoritative source files.
2. Reconcile supplied operations with current Django routes and frontend callers.
3. Implement the PAPER/LIVE contract migration and required data migration,
   preserving virtual and real authority separation.
4. Migrate affected callers before route removal; reconcile this cross-repository
   dependency with backend-first milestone delivery.
5. Generate `API-IMPLEMENTATION-MATRIX.md` with evidence-backed module, service,
   authorization, gates, test and caller mappings. Do not label a stub as
   `IMPLEMENTED_GATED` or invent implementation evidence.
6. Validate OpenAPI/AsyncAPI, migration compatibility, runtime behavior and all
   required CI checks, then obtain the required independent approval and merge.

No runtime routes, account data, provider credentials or financial activation
flags have changed in this preparatory work. No milestone is complete.

## Review gate

Backend main currently requires one approving review, dismisses stale approvals,
enforces protection for administrators, and requires `container`,
`exact-head-base-ci`, `secrets`, `validate`, and `orchestrator-contract` against an
up-to-date branch. These requirements must be rechecked on the final PR head.
