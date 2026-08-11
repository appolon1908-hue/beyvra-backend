# Withdrawal security

The real-withdrawal feature gate is the ultimate deny. Future eligibility additionally requires active/unfrozen account, approved KYC, cleared AML and sanctions, supported jurisdiction, no restriction, fresh authenticated session, recent MFA, verified destination outside cooldown, amount/velocity limits, risk policy, and manual review where required.

Policy `withdrawal-security-v1` defaults: session freshness 30 minutes, MFA freshness 10 minutes, sensitive-change cooldown 24 hours, and a configurable server-side transaction limit. Password/MFA/email changes, destination addition, new device, revoked/stolen/expired session and account freeze deny or require step-up/review. Maker and checker identities must differ. Generic support roles cannot approve.

Destination fields are `destination_id`, `account_ref`, type, asset/network, masked display, status, creation/verification/cooldown timestamps. States: `PENDING`, `VERIFIED`, `LOCKED`, `REVOKED`. Only deterministic syntax/network validation is allowed; validation never broadcasts.
