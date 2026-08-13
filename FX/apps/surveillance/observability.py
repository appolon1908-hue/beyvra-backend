from prometheus_client import Counter, Gauge, Histogram

EVENTS = Counter("beyvra_surveillance_events_total", "Surveillance indicators created", ("rule_type", "severity"))
CASES = Gauge("beyvra_surveillance_cases_open", "Open surveillance cases", ("severity",))
EVALUATIONS = Counter("beyvra_surveillance_rule_evaluations_total", "Surveillance rule evaluations", ("rule_type", "result"))
HITS = Counter("beyvra_surveillance_rule_hits_total", "Surveillance rule hits", ("rule_type", "severity"))
RESTRICTIONS = Gauge("beyvra_surveillance_restrictions_active", "Active surveillance restrictions", ("restriction_type",))
STP = Counter("beyvra_self_trade_preventions_total", "Self-trade attempts prevented", ("result",))
LATENCY = Histogram("beyvra_surveillance_evaluation_seconds", "Surveillance evaluation latency", ("result",))
DEAD_LETTERS = Counter("beyvra_surveillance_dead_letter_total", "Surveillance dead letters", ("failure_category",))
RECONCILIATION = Gauge("beyvra_surveillance_reconciliation_violations_total", "Current surveillance reconciliation violations", ("check",))
