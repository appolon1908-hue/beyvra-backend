# Realtime rollback

Rollback images preserved before this checkpoint:

- `codestra-backend:staging-ws-gateway-20260805`
- `codestra-frontend:staging-ws-gateway-20260805`

Rollback consists of restoring those images through the existing staging
compose projects and re-enabling legacy routes. No production deployment or
database destructive operation is part of this migration.
