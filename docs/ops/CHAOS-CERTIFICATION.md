# Chaos certification

Faults require test/staging identity, verified backup, and every live-value flag false. Each injection is cleanup-scoped. Scenarios run singly, then restore readiness and reconcile. No fault was injected into the shared running host during local certification; staging chaos remains externally blocked.
