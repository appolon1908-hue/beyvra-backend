# Institutional trade allocation

One logical instruction exists per institution/trade and per idempotency key.
Lines retain target subaccounts. Fixed-percent allocation rounds down to 18
decimal places and assigns the deterministic remainder to the final ordered
member, proving line quantity equals canonical trade quantity. No give-up or
broker instruction is sent.
