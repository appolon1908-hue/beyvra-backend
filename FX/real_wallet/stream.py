"""Transport-neutral private stream protocol.

ASGI/WebSocket adapters can use this module without putting long-lived tokens
in URLs. Sequence validation is deliberately deterministic and tenant-neutral.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamCursor:
    channel: str
    sequence: int


def validate_resume(cursor: StreamCursor, latest_sequence: int) -> str:
    if cursor.sequence < 0 or latest_sequence < 0:
        raise ValueError("sequence must be non-negative")
    if cursor.sequence > latest_sequence:
        return "SNAPSHOT_REQUIRED"
    if cursor.sequence == latest_sequence:
        return "UP_TO_DATE"
    return "REPLAY_AVAILABLE"


def event_envelope(*, event_id, event_type, channel, subject, sequence, occurred_at, correlation_id, data):
    return {
        "event_id": str(event_id), "type": event_type, "version": "1", "channel": channel,
        "subject": subject, "sequence": sequence, "occurred_at": occurred_at,
        "correlation_id": str(correlation_id), "data": data,
    }
