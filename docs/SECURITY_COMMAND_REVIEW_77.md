# Compatibility security command integration (#77)

This source-only repair integrates the original command, view and serializer
changes with protected main without downgrading its newer dependencies, identity
safeguards, email destination policy or release machinery. It changes no runtime
configuration and authorizes no external effect or production deployment.

## Corrections

A missing singleton now requires `If-Match: NONE`; an arbitrary stale value cannot
create a missing policy. The persistent administrator row serializes first policy
creation because an absent policy has no row to lock. Existing target rows remain
locked through their version check and mutation. Out-of-tenant or nonexistent
user targets return not-found rather than becoming creatable singletons.

Permission and database lookup failures are no longer caught and treated as a
missing object. Rejected handler responses roll back the full command transaction,
including writes performed during legacy validation. Exact durable replays still
precede current-version validation, and empty 204 responses remain replayable.
Both request and optional correlation IDs must be UUIDs.

The original six command tests moved unchanged from `security/tests.py` to
`security/tests/test_commands.py`. Main now has a `security.tests` package; leaving
the command suite in the sibling module would hide it from normal package imports.
The obsolete empty sibling module is removed; existing package tests are retained.

Seven additional tests cover absent-row preconditions, valid first creation and
replay, UUID validation, permission/database failure propagation, full rollback of
rejected commands, and two simultaneous first writers against PostgreSQL.

## Validation authority

The dedicated Security command safety workflow executes `security.tests` against
PostgreSQL 16 at the exact PR head, including the new concurrency regression.
Existing CI is retained unchanged. New-head CI and eligible independent review
must pass before protected merge; historical pass counts are not current evidence.
