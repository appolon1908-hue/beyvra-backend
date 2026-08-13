# Event Subject Registry

The outbox event type is the JetStream subject. There is no `application.*`
translation or fallback.

| Domain/event | Versioned subject | Producer | Stream | Consumer/durable | Ack and idempotency | Business effect |
|---|---|---|---|---|---|---|
| order lifecycle | `trading.order.*.v1` | canonical trading service | `TRADING_EVENTS` | simulation execution / `beyvra-simulated-execution-v1` | explicit ack; event ID + order idempotency key | canonical order transition |
| execution lifecycle | `trading.execution.*.v1` | execution authority | `TRADING_EVENTS` | post-trade/realtime consumers | explicit ack; execution ID/inbox | fill and evidence |
| trade lifecycle | `trading.trade.*.v1` | post-trade capture | `TRADING_EVENTS` | valuation/post-trade/realtime | explicit ack; execution/source event unique | canonical trade capture/projection |
| settlement workflow | `post_trade.settlement.*.v1` | post-trade service | `POST_TRADE_EVENTS` | workflow/realtime consumer | explicit ack; instruction idempotency key | provider-neutral workflow only |
| valuation | `valuation.*.v1` | valuation service | `VALUATION_EVENTS` | read-model/realtime consumer | explicit ack; event ID/inbox | valuation projection |
| treasury | `treasury.*.v1` | simulation treasury | `TREASURY_EVENTS` | read-model/realtime consumer | explicit ack; event ID/inbox | simulation projection |
| surveillance evidence | `regulatory.surveillance.*.v1` | surveillance service | `REGULATORY_EVENTS` | operator/evidence consumer | explicit ack; event ID/inbox | evidence/case projection |
| compliance | `compliance.*.v1` | compliance service | `COMPLIANCE_EVENTS` | account/realtime consumer | explicit ack; event ID/inbox | eligibility projection |
| market data | `market.>` | market-data authority | `MARKET_EVENTS` | realtime bridge | explicit ack; provider event/sequence | public market projection |
| news/economic | `news.>` | news authority | `NEWS_EVENTS` | realtime bridge | explicit ack; provider article/event ID | public news projection |
| private delivery | `private.>` | projection bridges | `PRIVATE_ACCOUNT_EVENTS` | realtime bridge | explicit ack; envelope event ID | account delivery only |
| system | `system.>` | platform operations | `SYSTEM_EVENTS` | operations/realtime bridge | explicit ack; event ID/inbox | operational projection |

All application consumers that can cause a durable business effect use
`ProcessedEvent(event_id, consumer_name)` via `consume_once`; the uniqueness
constraint and transaction roll back a concurrent losing mutation. Publisher
redelivery uses `Nats-Msg-Id=event_id`; poison events exhaust bounded retries
into the application dead-letter state.

```text
PUBLISHED_SUBJECTS_WITHOUT_STREAM=0
DUPLICATE_EVENT_SUBJECT_AUTHORITIES=0
OUTBOX_TRANSACTION_GAPS=0
INBOX_DEDUP_GAPS=0
UNIDEMPOTENT_REDELIVERABLE_CONSUMERS=0
```
