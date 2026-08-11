# Simulated Trading SLIs and Initial Engineering SLOs

These are staging engineering targets, not production commitments.

| SLI | Initial target | PromQL |
|---|---:|---|
| API availability | 99.9% / 30d | `1 - sum(rate(beyvra_http_requests_total{status_class="5xx"}[30d])) / sum(rate(beyvra_http_requests_total[30d]))` |
| API p95 | <500ms | `histogram_quantile(0.95,sum by(le)(rate(beyvra_http_request_duration_seconds_bucket[10m])))` |
| Order processing p95 | <750ms | `histogram_quantile(0.95,sum by(le)(rate(beyvra_trading_order_processing_duration_seconds_bucket{simulation="true"}[10m])))` |
| Outbox delay | <30s | `max(beyvra_outbox_oldest_pending_age_seconds)` |
| Execution delay | measure baseline | `histogram_quantile(0.95,sum by(le)(rate(beyvra_sim_settlement_duration_seconds_bucket[10m])))` |
| Realtime delivery | no failures | `sum(rate(beyvra_realtime_publish_failures_total[10m])) == 0` |
| Market freshness | policy bound | `max(beyvra_market_data_age_seconds) < bool 30` |

Measure representative traffic before tightening. MTTD, fault duration, service
recovery, pipeline recovery, and backlog drain are staging measurements only and must
not be presented as production MTTR.
