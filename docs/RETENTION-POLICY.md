# Retention policy model

Each policy version defines `data_category`, `retention_period`, legal-hold behavior, deletion method, anonymization method, and policy version. Durations are intentionally unset: **EXTERNAL_POLICY_REQUIRED=YES**. Legal/compliance must approve jurisdictional durations before automation is enabled.

An active hold prevents deletion. Permitted direct identifiers may be anonymized while financial, compliance, and audit authority remains intact. Backup expiry is separate from live deletion; a restore can reintroduce pre-deletion data and therefore requires replay of the deletion/anonymization ledger before service restoration.
