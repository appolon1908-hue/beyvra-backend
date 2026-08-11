# Institutional RBAC

Roles are `institutional_viewer`, `institutional_operations`,
`institutional_risk_analyst`, `institutional_manager`, `custody_operations`,
and `clearing_operations`. Customer membership grants customer-safe reads only.
Sensitive changes use `InstitutionalOperatorAction`; its database constraint
forbids self-approval. Support and generic membership do not grant operator
access.
