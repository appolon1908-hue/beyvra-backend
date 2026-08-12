# State-machine inventory

| Domain | Implementations | Status |
|---|---|---|
| Order | `apps.trading.domain.OrderState`, legacy `trade.demo_state`, execution mission states | CONFLICT |
| Execution | execution authority mission branch and provider-native states | UNMERGED |
| Post-trade | post-trade mission branch | UNMERGED |
| Settlement | backend post-trade projection and Financial Service monetary operation states | BOUNDARY AMBIGUOUS |
| Deposit/withdrawal/transfer | legacy wallet/payment, dormant real-wallet, Financial Service | CONFLICT |
| Account/KYC | user status, compliance `KycStatus`, institutional account states | CONFLICT |
| Provider | provider-governance status plus provider-native adapter states | NEEDS CANONICAL MAPPING |
| Incident | legacy security incidents, mission operational incidents, Financial Service incidents | AMBIGUOUS |

Direct model `.save()` paths in legacy APIs bypass canonical transition services. Transition-level evidence and correction/reversal paths require the combined branch.

