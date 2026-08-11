# Staging resume audit — 2026-08-06

The backend checkpoint was recovered at `382cad2`; both `25873ac` and
`a032eb3` are ancestors. The supplied Codestra frontend checkpoint is
`2c419f7`. The live trading frontend is separately deployed from
`realtime/frontend-manager` at `61684fcb`.

Baseline evidence: 43 focused backend tests after the provider-gate regression
was added, Django system check, and both frontend typecheck, lint, and
production builds pass.

The existing staging runtime on host `10.40.0.3` was reused: NATS 2.10.22 uses
verified mutual TLS, JetStream has eight streams and nine consumers,
Centrifugo 6.2.0 is healthy, and the realtime bridge is connected. `/ws/v2/`
upgrades successfully and authenticated `/ws/v1/` remains the rollback path.

Market, news, and calendar approvals remain pending. No provider, real-money
wallet, live trading, payment, or production order-routing capability was
activated.

## Rollback

The pre-change repository bundle and provider-directory snapshot are under
`/root/backups/codestra-provider-gate-20260806T2000Z/`. Restore source into a
new worktree from the bundle; do not overwrite the active worktree. The empty
provider-directory snapshot can be restored with `cp -a` only after stopping
provider consumers and validating the target paths.
