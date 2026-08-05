# V2 staging operations and verification

Health checks:

* `GET /api/v1/realtime/v2/health` (authenticated middleware health)
* Centrifugo internal `/health` and `/metrics`
* NATS internal `http://nats:8222/healthz` and JetStream `nats server check jetstream`

Smoke checks:

1. Create a Guest Demo and obtain a middleware connection token.
2. Connect to `wss://staging.codestra.cloud/ws/v2/connection/websocket`.
3. Subscribe to a permitted market channel; verify an unauthorized account
   channel receives a denial.
4. Restart Centrifugo and reconnect; V1 remains the fallback while V2 is
   disabled.

Do not enable payments, real wallets, live trading or production V2 flags.
