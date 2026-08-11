# Beyvra Simulation SLI/SLO Definitions

These are initial staging engineering targets, not contractual production SLOs.

| Indicator | PromQL | Initial target |
|---|---|---|
| API availability | `1-sum(rate(beyvra_http_requests_total{status_class="5xx"}[30d]))/clamp_min(sum(rate(beyvra_http_requests_total[30d])),0.0001)` | >=99.9% |
| API p50/p95/p99 | `histogram_quantile(P,sum by(le)(rate(beyvra_http_request_duration_seconds_bucket[10m])))` where P is `.50`, `.95`, `.99` | p95 <500ms |
| Order preview p95 | `histogram_quantile(.95,sum by(le)(rate(beyvra_http_request_duration_seconds_bucket{route_template=~".*/orders/preview"}[10m])))` | <500ms |
| Order acceptance p95 | `histogram_quantile(.95,sum by(le)(rate(beyvra_trading_order_processing_duration_seconds_bucket{simulation="true"}[10m])))` | <750ms |
| Outbox age | `max(beyvra_outbox_oldest_pending_age_seconds)` | <30s |
| Execution/settlement p95 | `histogram_quantile(.95,sum by(le)(rate(beyvra_sim_settlement_duration_seconds_bucket[10m])))` | baseline before tightening |
| Realtime reconnect success | `sum(increase(beyvra_realtime_snapshot_recovery_total{result="success"}[10m]))/clamp_min(sum(increase(beyvra_realtime_sequence_gap_total[10m])),1)` | 100%; reconnect <10s |
| Market freshness | `max(beyvra_market_data_age_seconds)` | within configured policy |
| Worker availability | `min(beyvra_worker_up{worker_type=~"outbox_publisher|execution_consumer|realtime_bridge"})` | 1 |

Raw identifiers are never labels. Windows require representative minimum traffic.
Staging MTTD/recovery measurements must not be described as production MTTR.
