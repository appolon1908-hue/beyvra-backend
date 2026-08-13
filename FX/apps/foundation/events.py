import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class EventEnvelope:
    event_id: uuid.UUID
    event_type: str
    schema_version: int
    occurred_at: datetime
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    tenant_ref: str
    payload: dict

    def as_dict(self):
        value = asdict(self)
        return {key: item.isoformat() if hasattr(item, "isoformat") else str(item) if isinstance(item, uuid.UUID) else item for key, item in value.items()}


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
