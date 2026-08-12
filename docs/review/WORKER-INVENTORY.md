# Worker and consumer inventory

Static extraction identified at least 15 WebSocket consumer classes in the checked-out backend:

- canonical compatibility gateway: `ws.CanonicalGatewayConsumer`
- external API socket: `ws.WebsocketConsumer`
- real-wallet stream consumer
- five portfolio consumers
- five `wsnotifications` consumers

Additional process workers include the application outbox publisher, demo-event publisher, realtime V2 bridge, transactional-email worker, notification webhook delivery, news compatibility publisher and mission-branch Financial Service/event consumers.

Five simultaneous WebSocket route families remain: `/ws/v1/`, `/ws/v1/real-wallet/`, `/ws/external-api/`, legacy `/ws/market|trades|admin|users/`, and public `/ws/v2/` through Centrifugo. Only `/ws/v2/` is intended canonical.
