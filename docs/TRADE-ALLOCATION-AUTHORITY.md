# Trade Allocation Authority

`TradeAllocationService` defaults retail trades directly to their originating economic account. It rejects tenant/account mismatches and requires allocated quantity to equal trade quantity exactly using `Decimal`. Subaccount and strategy fields are contract-ready but no unsupported account hierarchy is fabricated.
