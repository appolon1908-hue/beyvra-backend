# Institutional account authority

`InstitutionalAccount` is separate from a tenant and from individual users.
It has explicit type, status, effective dates, base currency, and optional
opaque legal/jurisdiction references. `UNKNOWN` never grants access. Customer
APIs resolve accounts only through authenticated organization membership;
arbitrary public lookup is absent.
