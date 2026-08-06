"""Provider-neutral market event validation.

The validator is transport-independent and is suitable for NATS/JetStream,
HTTP replay, or an ASGI adapter. It rejects duplicates and out-of-order events
and requests bounded snapshot recovery on gaps.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    schema_version: str
    channel: str
    sequence: int
    occurred_at: str
    payload: dict


class SequenceTracker:
    def __init__(self, max_replay: int = 500):
        self.last_sequence: dict[str, int] = {}
        self.seen_ids: set[str] = set()
        self.max_replay = max_replay

    def accept(self, event: MarketEvent) -> str:
        if not event.event_id or not event.schema_version or event.sequence < 0:
            return "INVALID"
        try:
            datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return "INVALID"
        if event.event_id in self.seen_ids:
            return "DUPLICATE"
        previous = self.last_sequence.get(event.channel)
        if previous is not None and event.sequence <= previous:
            return "OUT_OF_ORDER"
        if previous is not None and event.sequence - previous > self.max_replay:
            return "SNAPSHOT_REQUIRED"
        self.seen_ids.add(event.event_id)
        self.last_sequence[event.channel] = event.sequence
        return "ACCEPTED"
