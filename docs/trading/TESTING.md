# Trading testing

Run the backend sequence-validator and demo-market suites, frontend typecheck,
Vitest, and production build in isolated staging. Security tests must cover
tenant/channel authorization, SSRF and content sanitization, sequence
manipulation, cache isolation, and stale-feed handling. Performance values must
be measured from a staging harness; no target is claimed without evidence.
