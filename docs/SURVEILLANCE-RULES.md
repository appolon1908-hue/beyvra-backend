# Surveillance Rules

Rules are database-versioned with effective intervals, bounded safe parameters, severity, asset class, rule version and policy version. Seeded rules cover STP, restricted instruments, wash-like balance, spoof-like rapid large cancels, multi-level layering, excessive cancels, rapid flips, and order-rate anomalies.

Threshold changes require a new version and effective timestamp. Unknown or stale market data cannot support a price-abuse conclusion; price-deviation expansion must use canonical instrument mappings and fresh authoritative market observations.
