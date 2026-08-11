# Realtime deployment checkpoint

Current staging deployment uses Django web/Daphne and Redis. Centrifugo/NATS
must be private, version-pinned, health-checked, resource-limited and exposed
only through the approved TLS proxy.
