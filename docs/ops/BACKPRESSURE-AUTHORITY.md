# Backpressure authority

Policies use warning, critical, recovery, and cooldown thresholds. Committed state, audit, and risk events may never be dropped. Only noncritical telemetry is droppable. Permitted controls include throttle, reject new work, pause optional consumers, read-only, simulation-only, and halt risk-increasing action.
