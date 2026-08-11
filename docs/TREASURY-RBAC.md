# Treasury RBAC

Roles: `treasury_viewer`, `treasury_analyst`, `treasury_manager`, `collateral_operations`, and `liquidity_risk`. Customer reads require tenant membership. Operator reads require a treasury role. Simulation actions require analyst/manager/risk scope. Critical exception resolution rejects self-checking via maker reference. Generic support has no treasury mutation permission.
