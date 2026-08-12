# Platform SRE readiness evidence

Generated 2026-08-12 UTC for branch `feat/platform-sre-release-safety`, based on `280d698091c9e8391c2a020ed263f3c7c6a084dd`. This repository evidence certifies local/fixture readiness only. Exact final commit and immutable image digest are attached to the draft PR after publication.

## Results

- PostgreSQL 16 migration from zero: PASS (183 total applied migrations after platform changes)
- Platform migrations: rollback PASS, reapply PASS, drift NONE
- Django system check: PASS
- Platform authority tests: 33 PASS
- Full backend suite: 359 PASS
- OpenAPI generation/validation: PASS; SHA-256 `1e6926f7905139f50e8e50e83dbe429954839339bd3f223a65999c55c6c9fa9b`
- Operational routes: 28, duplicate paths: 0
- Secret scan: PASS, findings 0
- dependency/config filesystem scan: PASS, critical/high findings 0
- Backup/restore: PASS; archive SHA-256 `af244eea06c3193190b65d7c3d79380ceb3e0957a8e7695aaeb9a1cf41a0b306`; observed local restore 10,640 ms
- Restored system check: PASS; failed reconciliations: 0
- Local public-capability rate policy: 30 requests/test window before deliberate 429 backpressure; declared safe fixture limit 21 (70%)
- Fixture latency at 30-request defined peak after warm-up: p50 0.9771 ms, p95 1.1041 ms, p99 1.1332 ms
- In-process kill hierarchy evaluation across six consumers: 0.003807 ms; runtime propagation remains staging-blocked

## External boundaries

No isolated staging deployment, real service chaos, production traffic, regional failover, or WAL archive is authorized from this repository. Therefore staging, runtime chaos/recovery, runtime SLO achievement, and PITR are not self-certified. No Financial Service or production state changed.
