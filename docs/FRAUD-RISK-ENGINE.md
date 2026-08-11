# Fraud risk engine

`evaluate_account_risk()` is server authority and returns `ALLOW`, `STEP_UP`, `REVIEW`, or `DENY`, canonical reason codes, a policy version, and evaluation time. Active freezes always win. New device/network and recent credential changes step up; session/velocity/review signals route to review; high-risk actions and failed-login bursts deny. Signals are evidence inputs, not claims of fraud or IP geolocation certainty.

Policy changes require security review and version increments. Decisions and manual overrides must emit append-only audit and transactional outbox events.
