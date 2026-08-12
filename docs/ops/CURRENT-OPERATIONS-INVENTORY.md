# Current operations inventory

Candidate base: `280d698091c9e8391c2a020ed263f3c7c6a084dd`; branch `feat/platform-sre-release-safety`. The control plane is stacked on the approved treasury-readiness candidate pending PR 43 merge.

The repository already had `/health/`, Prometheus middleware, an outbox heartbeat, PostgreSQL/Redis/NATS configuration, Grafana/Prometheus assets, and immutable application audit/outbox primitives. It lacked a unified service registry, SLI/SLO definitions, capacity evidence, backpressure policy, operational mode resolution, governed kill switches, immutable release/evidence manifests, configuration drift registry, incident authority, restore manifests, and full-stack reconciliation authority.

Runtime discovery on 2026-08-11 found the application stack plus PostgreSQL, Redis, NATS, JetStream-oriented workers, Prometheus 3.13.0, Grafana 13.1.0, Alertmanager, exporters, and Loki. This is inventory evidence, not production certification. No runtime configuration or production service was changed.

Safety flags are code-pinned false for real trading, external execution, settlement, treasury transfers, broker routing, and FIX live sessions. Application Financial PostgreSQL access remains absent.
