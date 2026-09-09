# Institutional RBAC

Roles are `institutional_viewer`, `institutional_operations`,
`institutional_risk_analyst`, `institutional_manager`, `custody_operations`,
and `clearing_operations`. Customer membership grants customer-safe reads only.
Sensitive changes use `InstitutionalOperatorAction`; its database constraint
forbids self-approval. Support and generic membership do not grant operator
access.

Institutional viewers and risk analysts have read access only. Mutations require an
active operations or manager membership in the target tenant; a writable role in
another tenant cannot elevate read-only access. Inactive tenants grant no operator
scope. Institution references are validated as UUIDs before database lookup.

Customer institutional reads use the shared tenant resolver. Accounts with more
than one active membership must send `X-Organization-ID`; missing selection
returns 400 and unauthorized, inactive or malformed selections return 403.
