# Realtime target contract

`beyvra-asyncapi-3.0.yaml` reconstructs the revised written PAPER/LIVE mission.
It is not the original supplied attachment and does not certify the current
runtime. Reconcile the source attachment before declaring B00 complete.

The contract declares the thirteen shared channel families over `/ws/v2`,
account/customer/workforce authorization metadata, REST snapshot recovery, and
typed event payloads. Decimal amounts are strings. Sequence numbers are positive
integers within JavaScript's exact range. Optional market fields do not require
providers to fabricate unavailable prices or volume.

Run the same checks as the read-only contract CI job from the repository root:

```sh
python3 -m pip install PyYAML==6.0.3 jsonschema==4.26.0 rfc3339-validator==0.1.4
npm ci --prefix contracts/tooling --ignore-scripts --no-fund --no-audit
node scripts/validate_asyncapi.mjs
python3 -m unittest discover -s scripts -p 'test_asyncapi_contract.py'
```

The pinned AsyncAPI parser checks document structure and references. Python
regressions check payload schema validity, RFC3339 timestamps, exact channel
coverage, private scope requirements, decimal serialization, sequence bounds and
public-market scope exclusions. Duplicate YAML keys fail instead of silently
overwriting an earlier declaration.

These are contract tests. They do not establish authorization enforcement,
monotonic allocation, stream ordering, event delivery, payload/envelope/channel ID
equality, or recovery correctness. B17 must implement and test those runtime
properties. In particular JSON Schema cannot compare two sibling identifier
values; publishers and subscribers must enforce scope equality. B17 must also
reconcile event-type identifiers with the existing outbox before runtime rollout.

Validation dependencies are development-only, locked in `contracts/tooling`,
installed without lifecycle scripts, and excluded from container build context.
