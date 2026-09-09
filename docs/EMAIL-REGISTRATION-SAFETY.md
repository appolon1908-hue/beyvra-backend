# Local registration response safety

Registration uses one persisted pending-registration lifecycle for available and
already registered addresses. Both receive UUIDv4 identifiers, the same status
response fields, decreasing challenge/registration countdowns, and the same
expiry, resend cooldown and verification-attempt rules. Repeated and concurrent
requests reuse the active row. After expiry, both flows create a new identifier.

An internal `is_decoy` flag prevents an existing-address registration from sending
OTP or welcome mail, activating an account, issuing authentication cookies, or
changing the existing account. The flag is not returned by the public API. Even
a matching challenge code cannot activate a decoy. Migration 0038 adds the flag
with a false default for existing pending registrations.

The registration API validates the email, bounded password/name/locale fields,
and explicit boolean legal acceptance. The legacy view delegates to the same
implementation. Status and resend behavior are tested together with registration;
matching only the initial response shape is insufficient.
