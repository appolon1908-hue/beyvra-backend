# FIX Gateway Readiness

The fixture gateway models Logon, Logout, Heartbeat, TestRequest, ResendRequest, SequenceReset, NewOrderSingle, Cancel, Replace, ExecutionReport, CancelReject and BusinessReject types. It exercises sequence gaps, resend requests, PossDup and execution-ID deduplication.

`build_fixture()` produces non-network protocol evidence. Order messages sent through `send()` raise `FIX_LIVE_SESSION_DISABLED`; no transport, session credential, or broker connection exists. Persistent sequence storage is deferred until a separately approved paper FIX session exists.
