# FIX Sequence Gap

Enter `RECOVERING`, issue a bounded ResendRequest, apply PossDup deduplication, reconcile execution IDs, and return to `LOGGED_ON` only when the gap is closed.
