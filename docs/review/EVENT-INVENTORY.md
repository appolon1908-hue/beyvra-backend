# Event inventory

| Family | Producer/outbox | Transport subject | Consumer | Finding |
|---|---|---|---|---|
| Demo order/execution | `trade.DemoEventOutbox` | `private.order.*`, `private.trade.*` | realtime bridge/Centrifugo | account scoping exists |
| Application domain | `foundation.OutboxEvent` | `application.<event_type>` | no matching checked-in stream | P1 delivery gap |
| News/calendar | consolidated foundation outbox with deprecated alias | `news.*` | realtime bridge | duplicate compatibility publisher remains |
| Real wallet | `real_wallet.OutboxEvent` | not integrated with canonical application publisher | webhook/realtime workers | noncanonical shadow domain |
| Financial | Financial Service transactional outbox | `financial.*` / `FINANCIAL_EVENTS` | backend financial consumer on mission branch | isolated and fail-closed |
| Provider market data | governed provider pipeline | `market.*` | bridge/frontend | implemented on unmerged mission stack |

Canonical event identity must be the authoritative outbox UUID with `Nats-Msg-Id`; every business-effect consumer requires a durable inbox or equivalent unique database claim.
