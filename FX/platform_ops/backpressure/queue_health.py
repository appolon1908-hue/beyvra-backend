from dataclasses import dataclass
@dataclass(frozen=True)
class QueueHealth: pending:int; ack_pending:int; redeliveries:int
def bounded(q,critical): return q.pending < critical and q.ack_pending < critical
