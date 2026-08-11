# Operational dashboards

Provision the six Grafana dashboard definitions in `dashboards/` from these bounded metric groups:

- **Beyvra / Account Security:** security-event rates by reason/risk, freezes, session revocations, ATO alerts.
- **Beyvra / Support Operations:** open cases, age, first response, resolution, escalation destination.
- **Beyvra / Reporting:** jobs by state/type, reconciliation failures, generation latency.
- **Beyvra / Privacy Operations:** exports by state, legal-hold blocks, anonymization outcomes.
- **Beyvra / Notifications:** create/send/fail/dead-letter rate and delivery latency by category/channel.
- **Beyvra / Operator Control:** rejected actions, approvals, self-approval attempts, audit failures.

No dashboard query or label may contain direct or opaque customer identifiers. Alert rules live in `operations-alerts.yml`.
