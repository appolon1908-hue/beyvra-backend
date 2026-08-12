# Broker Health and Circuit Breakers

Health is `HEALTHY`, `DEGRADED`, `UNAVAILABLE`, `HALTED`, or `UNKNOWN`; circuit state is `CLOSED`, `OPEN`, or `HALF_OPEN`. Three fixture failures open the circuit for 30 seconds. Disabled providers do not route and should not page.
