# Operator control inventory

Django admin, broad `IsAdminUser` endpoints, custom user/KYC tools, wallet views, security lists, and provider settings predate the scoped control plane. They are classified LEGACY and must not be treated as authority for new operations. Direct KYC mutation, user export, and global policy endpoints require follow-up containment before production use.

The canonical namespace is `/api/internal/v1/`, backed by explicit tenant roles, masked views, audit, rate limits, and maker/checker. Provider and financial feature state is view-only and disabled. No operator endpoint edits a ledger or activates a provider.
