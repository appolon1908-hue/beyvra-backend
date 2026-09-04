# Beyvra Integration Fabric Branch Map

Parent contract: `integration/codestra-beyvra-fabric-v2`

Focused implementation branches:

- `feature/beyvra-operations-api-v1`
- `feature/beyvra-report-automation-v1`
- `feature/beyvra-support-escalation-v1`
- `feature/beyvra-webhook-reconciliation-v1`
- `test/beyvra-fabric-contracts-v1`

Do not bundle trading, wallet, payment, custody, provider, deployment, or frontend work into these branches. Each branch requires exact-head CI, independent review, isolated staging, rollback evidence, and capability-specific approval.
