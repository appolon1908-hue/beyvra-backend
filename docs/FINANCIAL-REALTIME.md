# Financial realtime and gap recovery

The private `/ws/v2/` contract defines four versioned financial event topics:

- `wallet.updated.v1:{authenticated_user_id}`
- `deposit.updated.v1:{authenticated_user_id}`
- `withdrawal.updated.v1:{authenticated_user_id}`
- `transfer.updated.v1:{authenticated_user_id}`

Subscription ownership is constructed from the authenticated session. A
client-supplied `user_id`, tenant, account, substring match, or event payload
cannot expand access. Tokens carry the server-derived tenant and subject; the
private proxy performs the same exact template match.

Each event has a positive monotonic `sequence`. The application projection
cursor is uniquely scoped by tenant, authenticated subject, and event type.
Exact duplicates are ignored, stale events cannot move state backwards, and a
different event reusing a sequence is a conflict. A forward gap is never
applied as success.

On a gap, the consumer:

1. pauses application of that topic;
2. fetches the registry-declared canonical REST snapshot;
3. verifies snapshot tenant and authenticated subject;
4. replaces the projection and cursor with the snapshot sequence/version;
5. resumes only from the next sequence.

Snapshot recovery is exercised with an isolated deterministic adapter. While
`REAL_WALLET_READ_ENABLED=false`, the real wallet snapshot route remains
`FEATURE_DISABLED`; realtime support does not bypass that gate. Application
projection rows are non-authoritative and contain no ledger postings.

Realtime infrastructure and financial publication remain disabled by default.
No Centrifugo, NATS, Financial Service, custody, payment, or blockchain request
is made by the projection tests.
