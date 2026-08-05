# Codestra `/ws/v1/` staging load report

Run date: 2026-08-05  
Scope: staging only; no production, payment, or real-money systems were changed.

## Changes applied during the run

- Pinned staging `REDIS_HOST` to `backend-redis-1`. The shared Docker network
  also exposed another `redis` alias, which caused web and Daphne to resolve
  different Redis instances and produced intermittent ticket cache misses.
- Initialized gateway teardown state before authentication so rejected
  handshakes cannot raise during `disconnect`.
- Raised staging Daphne, Nginx, and Redis `nofile` limits to 65536.

## Progressive results

The harness used the authorized staging Demo-session and websocket-ticket APIs,
then subscribed each socket to `market.status`, `notification`, and
`demo.order`. No order was submitted.

| Connections | Connected | Failed | Connect P95 | Ack P95 |
|---:|---:|---:|---:|---:|
| 1 | 1 | 0 | 26 ms | 27 ms |
| 10 | 10 | 0 | 78 ms | 93 ms |
| 50 | 50 | 0 | 903 ms | 982 ms |
| 100 | 100 | 0 | 1,732 ms | 1,944 ms |
| 250 | 250 | 0 | 3,992 ms | 4,545 ms |
| 500 | 80 | 420 | 9,823 ms | 11,098 ms |

At 50 concurrent connections, fan-out with 1, 5, and 10 valid subscriptions
per connection completed with 0 failures. Ack P95 was 983 ms, 826 ms, and
1,013 ms respectively. Ten subscriptions was the maximum tested valid fan-out
for this gateway harness.

The 500-connection failures were HTTP 502 upstream resets after Daphne
saturation. Before the file-descriptor fix, the same test also produced
`EMFILE` errors while opening Redis connections.

## Security and correctness checks

- Gateway authentication, forbidden-channel, duplicate-subscription, and
  account/tenant authorization tests pass.
- One-time websocket ticket replay: first connection `101`, replay `403`.
- Redis restart: new authenticated websocket connection succeeded.
- Daphne restart: new authenticated websocket connection succeeded.
- Frontend typecheck and lint pass.
- No dropped or duplicate business events were counted in this read-only load
  run; an event-publisher load test is still required before making that claim.

## Endurance status

The 30-second, 50-connection soak passed (50/50 connected, 0 errors). One-hour
and four-hour endurance runs were not executed in this validation window and
remain release blockers.

## Recommendation

Keep Django Channels for the current low-to-moderate staging scale (validated
through 100 connections). Do not treat 250 as a low-latency operating point,
and do not expose this deployment as a 500-connection target. Introduce a
versioned Centrifugo/NATS architecture behind a compatibility gateway if the
product requires 250+ concurrent realtime clients with predictable latency.
