# Realtime authorization

The `/ws/v2/` gateway is subscribe-only for browser clients. Accepted browser
actions are `subscribe`, `unsubscribe`, `resume`, and `ping`; browser-originated
`publish`, `broadcast`, `emit`, `push`, `send_market`, `send_news`, and
`inject_event` actions are rejected by the backend parser with a forbidden
error. The frontend must never be treated as a trusted market, news, or order
lifecycle publisher.

Trusted publication authority stays server-side:

- provider adapters and backend workers publish market quote and candle events;
- provider adapters and backend workers publish news and economic events;
- browser/session clients issue authenticated REST commands only, such as order
  preview/create/cancel, watchlist changes, compliance acknowledgements, and
  notification settings.

Knowing a channel name does not grant access. The gateway derives tenant
membership server-side, validates channels against the supported registry, and
keeps account/user-scoped channels bound to the authenticated principal. Browser
WebSocket `Origin` headers must match approved Beyvra frontend origins in
production. Missing Origin is allowed for non-browser server/test clients.
