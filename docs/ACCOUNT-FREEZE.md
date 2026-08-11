# Account freeze authority

`NONE` permits normal policy evaluation. `PARTIAL` blocks withdrawal, transfer, trading mutations, and credential-sensitive actions. `FULL` blocks every sensitive mutation. The backend enforces this after authentication and before downstream eligibility; support state and frontend state cannot override it.

Emergency freeze is available to an MFA-enrolled `security_manager`. Unfreeze uses an expiring `OperatorActionRequest`, independent manager approval, explicit execution, evidence/reason, and immutable before/after state hashes. The request and active freeze are row-locked; execution releases exactly one active tenant/account freeze. Self-approval and maker execution are forbidden. Provider activation, real-money activation, and direct financial/compliance override requests cannot execute in this service. Real-money capabilities remain disabled regardless of freeze state.
