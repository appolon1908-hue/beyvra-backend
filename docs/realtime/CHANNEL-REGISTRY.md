# Channel registry checkpoint

Current supported gateway channels are `market.candle:{symbol}:{interval}`,
`market.quote:{symbol}`, `market.status`, `demo.order`, `demo.execution`,
`demo.position`, and `notification`. Validation rejects unknown symbols,
intervals and private wallet/payment channels.

Target Centrifugo channel families require a separate authorization service and
must derive tenant, workspace, user and account scope from the authenticated
session rather than browser-supplied identifiers.
