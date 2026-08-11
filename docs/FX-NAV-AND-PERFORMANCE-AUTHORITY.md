# FX, NAV, and performance authority

FX conversion accepts same-currency identity, stored direct/inverse evidence, or a bounded USD/EUR triangulation whose complete rate chain is retained. Missing evidence returns `FX_RATE_UNAVAILABLE`.

Portfolio NAV is a simulation snapshot of classified cash/read-model value plus valued positions, receivables, payables, and accrued fees. Institutional NAV requires explicit child snapshots and matching currencies. No NAV is published as audited or real.

Simple return is available when opening value and cash-flow timing are complete. The models retain readiness for time-weighted and money-weighted returns, attribution dimensions, and benchmarks. A benchmark is never assigned automatically; absence is `NO_APPROVED_BENCHMARK`.

