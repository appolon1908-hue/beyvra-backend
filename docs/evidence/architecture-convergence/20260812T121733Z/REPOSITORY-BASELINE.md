# Beyvra architecture convergence repository baseline

Captured at `2026-08-12T12:17:33Z` before any mission repair. This evidence contains no credentials or secret values.

## Scope

| Logical repository | Path | Remote | Branch | HEAD | Base | Base SHA | Worktree |
|---|---|---|---|---|---|---|---|
| Backend | `/root/github-projects/backend` | `appolon1908-hue/trading-backend` | `feat/backend-p0-consolidation` | `34814195ab86b00ac2f5013bbf9946d732fb6c8e` | `origin/main` | `5a308d6bdb002ae718d8b62e664f02c6328962b0` | Dirty before mission |
| Frontend | `/root/github-projects/trading-frontend` | `appolon1908-hue/trading-frontend` | `feat/beyvra-canonical-api-realtime-prep` | `520bdb62e16a536da48d4bf3785f6ebed658564c` | `origin/main` | `f4d8f77befdaf39193b4693e009024c826ae8405` | Clean |
| Financial Service | `/root/github-projects/codestra-financial-service` | `Codestra-SRL/codestra-financial-service` | `feat/polygon-oms-custodial-adapter` | `157255f3a26ff42e06daf3203b0110a4a9bc2b8b` | `origin/main` | `b524ad9e8ca886773b413c1779940d5fc72e7d49` | Clean |
| Financial governance | `/root/github-projects/codestra-financial-governance` | `Codestra-SRL/codestra-financial-governance` | `agent/fix-exact-ci-fail-closed` | `fdd16c43141e224db785a055dd954ef245558af7` | `origin/main` | `55269a9032c2158591abc00247197f63c0b329ed` | Clean |

`/root/codestra-financial-governance` is a duplicate checkout at the same commit and is not a separate logical repository. `/srv/codestra` contains active edge configuration but is not a Git repository. Unrelated social/media repositories are excluded.

## Backend pre-existing changes

The following changes existed before this mission and are user-owned:

- modified: `FX/FX/settings.py`
- modified: `FX/apps/trading/api/errors.py`
- modified: `FX/integrations/views.py`
- modified: `FX/middleware/deprecation.py`
- modified: `FX/notifications/tasks.py`
- modified: `FX/notifications/tests.py`
- modified: `FX/notifications/views.py`
- modified: `FX/real_wallet/tests/test_boundary.py`
- modified: `FX/real_wallet/views.py`
- modified: `FX/users/email_verification.py`
- modified: `FX/ws/test_v2.py`
- modified: `FX/ws/v2.py`
- modified: `docker-compose.yaml`
- modified: `infra/realtime-v2/centrifugo.json`
- modified: `nginx/nginx.prod.conf.template`
- modified: `operations/check_nginx_upstreams.sh`
- modified: `scripts/check_public_identity.py`
- untracked: `backups/api-cert-20260811T135900Z-web-inspect.json`
- untracked: `backups/pre-sim-1a39650cb0698698e11fb49fef8519df7983fe5a.sql.gz`

No repository had a stash, merge, rebase, cherry-pick, revert, detached HEAD, or stale Git lock in progress.

## Safety state

- Production mutation: no
- Financial Service mutation: no
- Real trading activation: no
- External execution activation: no
- Real settlement activation: no
- Real-money activation: no
- Outbound live execution requests: zero
- Outbound live settlement requests: zero
- Real financial effects: zero

