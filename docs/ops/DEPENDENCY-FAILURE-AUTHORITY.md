# Dependency failure authority

Each dependency/capability pair owns timeout, mode, fallback, recovery, and fail-closed behavior. PostgreSQL write failure never reports success. NATS failure retains transactional outbox rows. Redis failure never relaxes quotas or security. Financial and broker mutations remain disabled; simulation is independent only where durable authority and fresh input remain available.
