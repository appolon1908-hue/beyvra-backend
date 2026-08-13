# Production-readiness remediation

Protected integration credentials are versioned AES-256-GCM envelopes. Runtime key material is loaded only from read-only secret files (`DATA_ENCRYPTION_KEY_FILE`, `WEBHOOK_MASTER_KEY_FILE`, `API_TOKEN_PEPPER_FILE`, and `PASSWORD_RESET_SIGNING_KEY_FILE`). The legacy database columns remain nullable for expand/contract rollback compatibility and are nulled by the encryption data migrations.

Service tokens are random bearer values shown once. Only a peppered HMAC digest, fingerprint, suffix, scopes, owner, environment, expiry, last-use and revocation metadata are stored.

`scripts/backup-encrypted.sh` creates a temporary custom-format PostgreSQL dump, encrypts it in the configured Restic repository, then removes the local dump. `scripts/restore-encrypted.sh` restores only to an explicitly supplied disposable directory. An approved off-server repository and its separately protected password file are still required before production.

Real CRM, email, SMS, social, payment, and production switches remain disabled in staging remediation.
