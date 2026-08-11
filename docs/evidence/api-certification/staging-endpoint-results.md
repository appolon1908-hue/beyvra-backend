# Staging endpoint certification

Certification date: 2026-08-11. Identity and data were synthetic. A pre-mutation PostgreSQL custom-format backup was created.

- Live/readiness: 200 with aggregate-only public responses; required dependencies ready
- Login, me, account, sessions, security events: PASS
- Compliance profile, requirements and restrictions: PASS
- Demo account, wallets, orders, trades and positions: PASS
- Notifications, support, reporting and privacy: PASS
- Status and features: PASS
- Real wallet read, deposit, withdrawal and transfer: `503 FEATURE_DISABLED`
- Canonical API verifier: 27/27 bounded probes PASS
- Fixture-only webhook verifier: PASS; 100 deliveries, 99 duplicate acknowledgements, one business effect, invalid signature rejected
- Application workers and realtime v2 gateway: healthy after rollout
- Financial Service: unchanged
- Production: unchanged

Certified candidate heads: backend `cbca88c87a1f9e8a1396c8a3c104a15936aff570`; frontend API-contract snapshot `3aa8252913a5f6e2432e9bb1ea0909e40c0210c2` (subsequent frontend commits only refreshed exact-head/base certification).

Bounded ten-request samples produced warm p50 values of 7–18 ms for instruments, notifications, support and activity reporting. The first `/me` sample included a cold-start outlier; no load test was performed.
