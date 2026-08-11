# Real Wallet Deployment

1. Apply migrations in an isolated financial database.
2. Seed all real-value feature flags as disabled.
3. Configure protected webhook master-key material through a secret file.
4. Configure only sandbox custody/chain/compliance adapters in staging.
5. Run the backend suite, migration check, OpenAPI validation, and synthetic
   provider/reconciliation tests.
6. Verify private ASGI routing and channel-layer health.
7. Obtain independent security, compliance, custody, backup, and release
   approvals before any feature flag is enabled.

Rollback is application-first: stop workers, deploy the prior image against
the forward-compatible schema, verify health and data integrity, then restore
the candidate. Do not destructively downgrade populated financial migrations.
