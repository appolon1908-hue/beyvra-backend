# Provider runtime binding

Preflight found the existing private staging runtime on `trading-network`:

- NATS `2.10.22`, JetStream enabled, eight streams and nine consumers.
- Centrifugo `6.2.0`, health endpoint HTTP 200.
- `realtime_bridge` connected to the same network.
- Backend environment has V2 flags enabled in staging.
- `/ws/v1/` remains the rollback gateway.

No duplicate runtime was created. Provider activation remains disabled pending
approval and credential references.
