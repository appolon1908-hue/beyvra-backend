# Observability authority

Metrics implement RED, resource, queue, dependency, kill-switch, and release signals with bounded labels. Structured logging recursively redacts secrets. Traces should use the current OpenTelemetry specification.

Version review on 2026-08-11: Prometheus 3.13 is the supported LTS line through 2027-07-31; Grafana 13 migration requires backups and compatibility review. Existing Prometheus 3.13.0 and Grafana 13.1.0 were inventoried and not upgraded. References: [Prometheus release cycle](https://prometheus.io/docs/introduction/release-cycle/), [Grafana v13 upgrade guide](https://grafana.com/docs/grafana/latest/upgrade-guide/upgrade-v13.0/), [OpenTelemetry specification](https://opentelemetry.io/docs/specs/otel/), [NATS monitoring](https://docs.nats.io/running-a-nats-service/nats_admin/monitoring), and [JetStream consumers](https://docs.nats.io/nats-concepts/jetstream/consumers).
