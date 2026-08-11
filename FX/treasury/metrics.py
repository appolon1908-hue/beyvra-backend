from prometheus_client import Counter, Gauge, Histogram

liquidity_available = Gauge("beyvra_treasury_liquidity_available", "Simulation liquidity available")
funding_requirements = Counter("beyvra_treasury_funding_requirements_total", "Simulation funding requirements")
funding_shortfalls = Counter("beyvra_treasury_funding_shortfalls_total", "Simulation funding shortfalls")
collateral_free_value = Gauge("beyvra_treasury_collateral_free_value", "Simulation free collateral value")
encumbered_value = Gauge("beyvra_treasury_encumbered_value", "Simulation encumbered value")
transfer_plans = Counter("beyvra_treasury_transfer_plans_total", "Simulation transfer plans")
buffer_breaches = Counter("beyvra_treasury_liquidity_buffer_breaches_total", "Simulation liquidity buffer breaches")
reconciliation_violations = Counter("beyvra_treasury_reconciliation_violations_total", "Treasury reconciliation violations")
exceptions_open = Gauge("beyvra_treasury_exceptions_open", "Open simulation treasury exceptions")
calculation_duration = Histogram("beyvra_treasury_calculation_duration_seconds", "Treasury calculation duration", ["operation"])
