# News provider governance

`newsdata` is registered as provider type `NEWS` and defaults disabled. Effective lifecycle: `DISABLED → CONFIGURED → CREDENTIAL_PRESENT → TECHNICALLY_CERTIFIED → LICENSE_VERIFIED → SECURITY_APPROVED → STAGING_APPROVED → PRODUCTION_APPROVED`.

The existing provider resolver requires enabled staging state, verified license, security/compliance/staging approval, current hash-bound approval, approved product/region/symbol, and a protected credential reference. Missing or ambiguous state returns `PROVIDER_NOT_AVAILABLE`. Archive additionally requires explicit account entitlement; otherwise it returns `CAPABILITY_NOT_AVAILABLE`.

Production remains unapproved. Alerts suppress intentionally disabled providers.

