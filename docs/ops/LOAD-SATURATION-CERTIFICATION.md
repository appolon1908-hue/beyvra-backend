# Load and saturation certification

Profiles must progress `BASELINE → 1X → 2X → 5X → PEAK_DEFINED`, stopping at unsafe saturation. Capture RPS, error and latency percentiles, CPU, memory, pools, Redis/NATS/JetStream state, queues, and worker lag. A pass requires zero lost committed events, no corruption, and bounded queues. Staging load is externally blocked in this candidate.
