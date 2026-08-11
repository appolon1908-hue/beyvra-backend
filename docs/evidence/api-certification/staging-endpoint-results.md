# Staging endpoint certification

Certification date: 2026-08-11. Identity and data were synthetic. A pre-mutation PostgreSQL custom-format backup was created.

- Live/readiness: 200; PostgreSQL, Redis and NATS ready
- Login, me, account, sessions, security events: PASS
- Compliance profile, requirements and restrictions: PASS
- Demo account, wallets, orders, trades and positions: PASS
- Notifications, support, reporting and privacy: PASS
- Status and features: PASS
- Real wallet read, deposit, withdrawal and transfer: `503 FEATURE_DISABLED`
- External provider webhook: disabled by governance; fixture-signature harness PASS
- Application workers and realtime v2 gateway: healthy after rollout
- Financial Service: unchanged
- Production: unchanged

Bounded ten-request samples produced warm p50 values of 7–18 ms for instruments, notifications, support and activity reporting. The first `/me` sample included a cold-start outlier; no load test was performed.
