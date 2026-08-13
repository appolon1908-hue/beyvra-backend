# Smart Order Routing

The router generates candidates, evaluates governance and venue constraints, snapshots market/pricing/risk inputs, scores eligible candidates, selects deterministically, persists evidence, audits the decision and emits an outbox event before execution. Zero candidates returns `ORDER_NOT_ROUTABLE`; arbitrary fallback is forbidden.
