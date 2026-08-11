# Account freeze authority

`NONE` permits normal policy evaluation. `PARTIAL` blocks withdrawal, transfer, trading mutations, and credential-sensitive actions. `FULL` blocks every sensitive mutation. The backend enforces this after authentication and before downstream eligibility; support state and frontend state cannot override it.

Emergency freeze is available to `security_manager`. Unfreeze uses an expiring `OperatorActionRequest`, independent manager approval, evidence/reason, and audit. Self-approval is forbidden. Real-money capabilities remain disabled regardless of freeze state.
