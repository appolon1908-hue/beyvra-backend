# Trading operations runbook

On provider outage, mark the feed `DISCONNECTED` or `STALE`, stop presenting
old ticks as live, open an incident, and use bounded reconnects. On a sequence
gap, request a snapshot and replay only within the configured retention window.
Disable the affected staging adapter on repeated validation failures. Never
route these events to real order execution.
