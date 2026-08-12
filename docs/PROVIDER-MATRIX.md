# Provider matrix

All candidates default to `DISABLED`; capability does not establish license, security, compliance, staging, or production approval.

| Provider | Categories | Candidate coverage | Adapter status | Approval |
|---|---|---|---|---|
| CoinGecko | market/reference data | crypto spot, metadata, markets, historical; WebSocket entitlement-dependent | governed REST contract + fixtures | not verified |
| Massive / Polygon | market/reference data | equities, options, indices, forex, crypto; coverage plan-dependent | legacy adapter inventory | not verified |
| Alpaca | market data, paper/live execution | equity/options/crypto depending agreement | candidate contract only | disabled |
| TradeStation | brokerage/market data | stocks, options, futures; SIM and live are distinct | contract candidate | disabled |
| IBKR | brokerage, Web/TWS/FIX | broad multi-asset; subscriptions/onboarding apply | architectural candidate | disabled |
| Plaid | banking link | account link/verification | interface only | disabled |
| Stripe | payment rail | funding/payout capability depends product/region | interface only | disabled |
| BitGo | custody | digital-asset custody workflows | interface only | disabled |
| Persona / Alloy | KYC/AML | identity/workflow capabilities contract-dependent | interface only | disabled |
| SES / SendGrid / Postmark | email | transactional email | interface only | disabled |
| Twilio / FCM | SMS/push | notification delivery | interface only | disabled |
| TaxBit / Ledgible | tax/reporting | tax lots/documents contract-dependent | interface only | disabled |

Recommendations require commercial, license, security, compliance, cost, data-quality, and sandbox evaluation. No primary vendor is selected by this repository.

Asset matrix: crypto has fixture-certified market and simulation support; equity/ETF/forex have canonical reference identities but no certified live feed; options and futures are modeled gaps; live execution is unsupported for every asset class.

