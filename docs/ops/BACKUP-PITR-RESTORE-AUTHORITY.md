# Backup, PITR, and restore authority

Backup manifests bind database version, release, size, SHA-256, encryption, storage, and verification. Recovery is a pass only after disposable restore, system/migration checks, reconciliation, and simulation smoke. WAL archive/restore configuration was not available to this repository, so PITR remains `EXTERNAL_INFRASTRUCTURE_BLOCKED`.
