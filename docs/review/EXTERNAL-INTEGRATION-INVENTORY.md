# External integration inventory

| Category | Provider/integration | Boundary status |
|---|---|---|
| Market data | Alpaca, CoinGecko, governed provider adapters | legacy direct clients coexist with provider governance |
| News | Alpaca news, NewsData mission adapter | multiple sources; canonical mission unmerged |
| OMS/custody | Polygon OMS | Financial Service adapter is canonical; application/browser direct access forbidden |
| Payments | Stripe, Binance Pay | legacy application integrations; real mutation gates disabled |
| Identity | Google OIDC | backend canonical auth adapter, disabled unless configured |
| Email/SMS | Django email provider, Twilio references | provider-neutral transactional outbox incomplete for all legacy paths |
| CRM | signed integration APIs | Beyvra and legacy Codestra header aliases coexist |
| Realtime | NATS/JetStream, Centrifugo, Redis/Channels | target and compatibility transports coexist |

No hardcoded production provider activation was authorized or exercised during audit.

