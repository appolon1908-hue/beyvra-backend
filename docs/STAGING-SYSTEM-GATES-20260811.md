# Staging system gates — 2026-08-11

The remaining staging system-review gates passed without enabling real money,
real trading, custody, payments, or external execution.

## Results

- Authenticated staging E2E: **PASS**, 30/30 Playwright scenarios.
- Public WebSocket load/soak: **PASS**, 520/520 authenticated connections held
  for 60 seconds with zero failures; p95 connection latency was 86.94 ms.
- Restart recovery: **PASS** for Centrifugo and NATS, with authenticated
  connectivity and application readiness confirmed after restart.
- Sequence gap recovery: **PASS**, 4/4 realtime unit tests; detected gaps require
  a canonical REST snapshot replacement before stream resume.
- Stale containers: the crash-looping simulated execution consumer and the
  unsupported temporary outbox publisher were removed. A supported canonical
  outbox publisher was subsequently deployed from Compose because readiness
  requires that service.
- Frontend bundle: the application chunk fell from approximately 1.8 MB to
  450.92 kB through deterministic vendor splitting. Large route/vendor chunks
  remain lazy-loadable and are recorded as a follow-up optimization target.

## Safety

The demo market fixture is deterministic, Decimal-safe, staging-only,
paper-trading-only, and disabled automatically during tests. It makes no
provider request and cannot authorize real financial activity.

`REAL_FINANCIAL_EFFECTS=0`; production was not changed.

## Evidence

- `docs/evidence/api-certification/staging-system-review-20260811.json`
- `docs/evidence/api-certification/staging-ws-load-20260811.json`
- `docs/evidence/api-certification/staging-ws-recovery-20260811.json`
