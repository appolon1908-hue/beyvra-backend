# V2 staging verification (2026-08-05)

## Deployment

* Backend commit: `29a95885727d2d9bcc75c2106caef17718c28be2`
* Frontend commit: `61684fcb987c32e52328c2eeaec0e117514dfd5a`
* Backend image: `codestra-backend:staging-ws-v2-20260805`
  (`sha256:9e2d91fbc32f51d276d446aac8b695728f18ad1c5747cf407ff331f590eaf053`)
* Frontend image: `codestra-frontend:staging-ws-v2-20260805`
  (`sha256:6e4e83f5b7b33c5534c10c8ed70df601fb6991d8ac0a99d402d745ab5f855ac7`)
* V1 rollback image remains preserved: `codestra-backend:staging-realtime-v1-loadfix2-20260805`.

## Passing checks

* Django system check: PASS.
* Frontend typecheck and lint: PASS.
* V2 contract tests (`ws.test_v2`): 2 passed.
* Centrifugo health and Prometheus endpoints: PASS.
* JetStream health: PASS; eight bounded file-backed streams and nine durable consumers survive NATS restart.
* NATS client traffic is currently private Docker-network traffic; internal TLS/mTLS is not yet enabled and remains a promotion blocker.
* Allowed market subscription: PASS.
* Cross-account private subscription: denied with `403 forbidden`.
* V1/V2 reverse-proxy paths are separate; no production services or flags changed.
* A synthetic event published through the private Centrifugo API was received by a `/ws/v2/` subscriber.

## Capacity observations

Ramp tests through the staging edge reached 249/250 connections with 147ms
P95. A 500-connection ramp reached 71/500 after the edge began returning 503
upstream failures; a separate reused-token run reached 478/500. This is a
staging capacity blocker, not an authorization success. The V2 target of 100%
at 500 connections is therefore **not met** and no endurance claim is made.

## Safety

`REALTIME_V2_ENABLED`, `REALTIME_V2_STAGING_ENABLED`, Centrifugo and NATS are
enabled only in the staging `.env` (0600, ignored). Production V2, real money,
live trading and payments remain disabled. `/ws/v1/` is retained for rollback.

## Remaining blocker

Run an isolated 500+ connection test from a dedicated load host and tune the
staging edge/upstream connection budget before promoting V2 beyond staging.
Do not delete V1 or claim `PASS_READY_FOR_WS_V2_REVIEW` until 500 connections,
token replay, restart recovery, and the 1-hour/4-hour endurance gates pass.
