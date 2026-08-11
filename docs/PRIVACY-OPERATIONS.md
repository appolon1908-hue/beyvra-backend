# Privacy operations

Privacy exports are idempotent asynchronous private jobs with schema version and 24-hour artifact expiry. They include entitled account/profile data, customer-visible support messages, notifications, and safe activity; they exclude secrets, staff notes, detection rules, risk levels/model internals, and other users. Artifact references are never returned by APIs. Authorized downloads are owner- and tenant-scoped and audited.

`PRIVACY-EXPORT-SCHEMA-v1` versions the export shape; it is not a claim of legal approval or a retention-duration decision. Legal retention decisions remain `EXTERNAL_POLICY_REQUIRED=YES`.

Deletion requests first check legal hold and record class. Required financial/compliance/audit records remain; eligible direct identifiers are anonymized without breaking opaque references. Storage and processor residency is unresolved and requires external legal review. Potential processors include KYC, email, support, analytics/monitoring, and future payment/custody providers; no DPA approval is claimed.
