# Market provider integration

Adapters expose historical candles, latest quotes, status, health,
capabilities, provenance, delay, and quality metadata. Requests are
server-side, bounded, timeout-limited, and circuit-breaker protected. Browser
clients never contact providers directly.
