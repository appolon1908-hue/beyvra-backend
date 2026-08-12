# Initial Architecture Convergence Audit

Captured: 2026-08-12 UTC, before integration changes.

```text
BACKEND_STARTING_HEAD=34814195f1ee6da7645c16552707754555729d05
FRONTEND_STARTING_HEAD=0b9074985554dc16fd6b89b8d306ce4ad66eb433
FINANCIAL_SERVICE_HEAD=157255f3a26ff42e06daf3203b0110a4a9bc2b8b

BACKEND_WORKTREE=CLEAN (/root/beyvra-architecture-convergence, created from frozen-bundle/feat/backend-p0-consolidation)
FRONTEND_WORKTREE=DIRTY (/root/front: client-portal/src/realtime/UnifiedRealtimeClient.ts and UnifiedRealtimeClient.test.ts modified)

OPEN_ARCHITECTURE_BRANCHES=29 backend feat branches, 19 frontend feature/agent branches, 4 Financial Service feature branches (local and remote inventory)
OPEN_PRS=64 (backend 43, frontend 18, Financial Service 3; counts include dependency/auth PRs and architecture PR stacks)
```

## Frozen conflict report

The pre-integration inspection found these convergence conflicts:

1. Architecture work is distributed across stacked and sibling mission branches rather than one integrated candidate. Several PRs target other feature branches, so merging every tip would duplicate shared history and obscure authority decisions.
2. Application financial modules (`FX/wallet`, `FX/payments`, `FX/trade/demo_engine.py`, and `FX/real_wallet`) coexist and need explicit simulation, legacy, read-model, or Financial Service boundary classification.
3. Trading, execution, risk, surveillance, pricing, post-trade, valuation, treasury, institutional, and provider work exists on independently developed branches and has not been certified as one Django model state.
4. The trading migration graph has independently introduced `0002`-era states and must be resolved from the combined model state, not by filename renumbering.
5. The publisher/JetStream subject contract is inconsistent: application event publication has used `application.<event_type>`, while checked-in stream coverage centers on `market.*`, `news.*`, `private.*`, and `system.*`.
6. More than one outbox/event-delivery pattern exists across legacy demo flows and the newer trading foundation; transaction and consumer deduplication guarantees need one canonical pattern.
7. Public realtime routing is inconsistent between frontend/Centrifugo/Nginx (`/ws/v2/` versus `/connection/websocket`).
8. Competing market channel dialects exist (`market.quote:{symbol}` and `market.{symbol}.quote`, plus corresponding candle and compatibility channels).
9. The checked-in OpenAPI contract is not authoritative and has duplicate route keys, including deposit/withdrawal paths.
10. Runtime and documented error shapes differ around `instance`, `request_id`, `code`, `message`, and `details`.
11. Legacy and versioned wallet/trading APIs can expose overlapping writable operations.
12. Legacy portfolio, trade, valuation, and frontend P&L calculations have not yet been reduced to one position and valuation authority.
13. Settings, root URLs, Docker/Compose, Nginx, workflows, and bootstrap changes are distributed across mission branches.
14. A prior audit reported approximately 663 MB of mutable database backup artifacts under a backend worktree; backups must be preserved outside the application worktree and ignored.

## Safety baseline

The frozen base hard-disables real trading and external execution in Django settings. The integration must additionally keep real settlement, real money, real deposits, real withdrawals, real treasury transfers, live broker routing, and FIX live sessions disabled. No production mutation is authorized.

This report is immutable audit evidence. Resolution status is tracked in `CONFLICT-REGISTER.md`.
