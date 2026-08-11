# FIX Gateway Readiness

The fixture gateway models Logon, Logout, Heartbeat, TestRequest, ResendRequest, SequenceReset, NewOrderSingle, Cancel, Replace, ExecutionReport, CancelReject and BusinessReject types. It exercises sequence gaps, resend requests, PossDup and execution-ID deduplication. Order messages raise `FIX_LIVE_SESSION_DISABLED`; no transport or credentials exist.
