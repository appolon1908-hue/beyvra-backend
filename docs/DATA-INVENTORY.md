# Data inventory

| Category | Class | Owner | System of record | Purpose | Access | Deletion/export |
|---|---|---|---|---|---|---|
| Identity, KYC, AML | RESTRICTED | Compliance | User/KYC service or approved provider | verification | compliance roles | policy/hold; user-safe export |
| Contact | CONFIDENTIAL | Product | User service | account communications | account + scoped staff | anonymize when allowed/export |
| Authentication | RESTRICTED | Security | Auth service | access control | security only | never export secrets |
| Security/device | CONFIDENTIAL | Security | Operations | ATO defense | security + safe support view | policy/hold; safe event export |
| Support | CONFIDENTIAL | Support | Operations | case resolution | scoped support | public messages export; internal notes excluded |
| Orders/trades/financial | RESTRICTED | Financial/Trading | Financial Service for real; simulation ledger for demo | execution/reporting | scoped roles | retained by external policy |
| Market | PUBLIC or contract-dependent | Markets | provider cache | product data | contract-defined | provider contract |
| Audit/logs | RESTRICTED | Security | audit/log platform | evidence/operations | authorized staff | immutable; policy/hold |
| Reports/privacy exports | RESTRICTED | Data Governance | Operations/private object store | customer access | owner + scoped operators | artifact TTL; source retained |
| Notifications | CONFIDENTIAL | Product/Security | Operations | account communications | owner + scoped operators | policy-defined |

PII includes name, email, phone, DOB, address, identity/tax documents, network and device identifiers, and free-form support content. No legal duration is asserted.
