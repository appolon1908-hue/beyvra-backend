from prometheus_client import Counter, Gauge


institutional_accounts_total = Gauge("beyvra_institutional_accounts_total", "Institutional accounts", ("status",))
institutional_subaccounts_total = Gauge("beyvra_institutional_subaccounts_total", "Institutional subaccounts", ("status",))
allocation_groups_total = Gauge("beyvra_allocation_groups_total", "Allocation groups", ("status",))
trade_allocation_exceptions_total = Counter("beyvra_trade_allocation_exceptions_total", "Trade allocation exceptions", ("reason",))
omnibus_attribution_mismatches_total = Counter("beyvra_omnibus_attribution_mismatches_total", "Omnibus attribution mismatches")
segregated_mapping_conflicts_total = Counter("beyvra_segregated_mapping_conflicts_total", "Segregated mapping conflicts")
broker_mapping_collisions_total = Counter("beyvra_broker_account_mapping_collisions_total", "Broker mapping collisions")
reconciliation_violations_total = Counter("beyvra_institutional_reconciliation_violations_total", "Institutional reconciliation violations", ("code",))
risk_limit_denials_total = Counter("beyvra_institutional_risk_limit_denials_total", "Institutional risk denials", ("scope",))
