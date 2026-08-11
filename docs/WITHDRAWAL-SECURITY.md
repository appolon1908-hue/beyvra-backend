# Withdrawal security

The real-withdrawal feature gate is the ultimate deny. Future eligibility additionally requires active/unfrozen account, approved KYC, cleared AML and sanctions, supported jurisdiction, no restriction, fresh authenticated session, recent MFA, verified destination outside cooldown, amount/velocity limits, risk policy, and manual review where required.

Policy `withdrawal-security-v1` defaults: session freshness 30 minutes, MFA freshness 10 minutes, sensitive-change cooldown 24 hours, and a configurable server-side transaction limit. Password/MFA/email changes, destination addition, new device, revoked/stolen/expired session and account freeze deny or require step-up/review. Maker and checker identities must differ. Generic support roles cannot approve.

Destination fields are `destination_id`, `account_ref`, type, asset/network, masked display, status, creation/verification/cooldown timestamps. States: `PENDING`, `VERIFIED`, `LOCKED`, `REVOKED`. Only deterministic syntax/network validation is allowed; validation never broadcasts.

The canonical `financial_destinations` table is tenant-, account-, and owner-scoped. It stores a masked display value and a keyed HMAC-SHA256 fingerprint; it has no raw address, bank detail, or provider customer reference column. The HMAC key must come from protected runtime configuration and creation fails closed when it is absent or too short. Cross-scope lookups return the same `DESTINATION_NOT_FOUND` result to prevent enumeration. A destination is ineligible unless it is verified, not revoked/locked, and past its server-side cooldown.

Current deterministic validation supports syntax and network separation for Ethereum, Bitcoin mainnet/testnet, and Solana. Fiat destinations accept only an opaque `provider:<provider>:customer:<reference>` identifier, never a bank account number. These validators prove shape only; they do not prove ownership and make no provider, node, or payment-rail request.
