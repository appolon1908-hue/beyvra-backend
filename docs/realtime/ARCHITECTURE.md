# Realtime architecture checkpoint

The current staging architecture is Django ASGI + Channels/Daphne, Redis
channel groups, a tenant-aware `/ws/v1/` gateway and a frontend market-feed
client. PostgreSQL remains authoritative for accounts, orders, trades and
wallets. The gateway is transport only.

The target Centrifugo/NATS design is a future staging track. It must be added as
a private, version-pinned deployment and validated through middleware before
any browser migration or legacy deletion.
