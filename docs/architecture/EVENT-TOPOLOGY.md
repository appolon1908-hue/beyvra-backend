# Canonical Event Topology

The event type is the JetStream subject. Publishers must not prepend `application.` or translate an event into a second authoritative subject.

```text
trading.>      order, execution, trade, and position projection events
post_trade.>   allocation and settlement workflow intent/projection
valuation.>    valuation/read-model events
treasury.>     simulation/read-model treasury events
regulatory.>   regulatory evidence events
compliance.>   compliance authority events
market.>       governed market data
news.>         governed news and economic events
private.>      account-scoped compatibility delivery
system.>       operational state
```

Every listed domain has checked-in JetStream stream coverage. Unknown/unqualified events fail publication with `NON_CANONICAL_EVENT_SUBJECT`; there is no `application.*` fallback.
