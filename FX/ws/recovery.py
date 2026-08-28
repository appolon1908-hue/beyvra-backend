import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.foundation.models import RealtimeChannelEvent
from ws.v2 import CHANNEL_REGISTRY, _channel_entry


DEFAULT_HISTORY_SIZE = 100


class SnapshotRequired(Exception):
    def __init__(self, current_sequence: int):
        self.current_sequence = current_sequence
        super().__init__("SNAPSHOT_REQUIRED")


@dataclass(frozen=True)
class StoredRealtimeEvent:
    event_id: str
    event_type: str
    channel: str
    sequence: int
    source: str
    occurred_at: datetime
    server_time: datetime
    data: dict

    def envelope(self) -> dict:
        occurred = self.occurred_at.isoformat()
        server_time = self.server_time.isoformat()
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": 1,
            "schema_version": 1,
            "type": self.event_type,
            "version": 1,
            "channel": self.channel,
            "sequence": self.sequence,
            "occurred_at": occurred,
            "server_timestamp": server_time,
            "server_time": server_time,
            "source": self.source,
            "payload": self.data,
            "data": self.data,
        }


def _stable_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _history_size(channel: str) -> int:
    _, entry = _channel_entry(channel)
    if not entry:
        return DEFAULT_HISTORY_SIZE
    return int(entry.get("history_size") or DEFAULT_HISTORY_SIZE)


def append_event(*, tenant_ref: str, channel: str, event_type: str, source: str, data: dict, occurred_at=None) -> StoredRealtimeEvent:
    server_time = timezone.now()
    occurred = occurred_at if hasattr(occurred_at, "isoformat") else server_time
    payload_hash = _stable_hash({"event_type": event_type, "source": source, "data": data})
    tenant = str(tenant_ref)
    with transaction.atomic():
        duplicate = (
            RealtimeChannelEvent.objects.select_for_update()
            .filter(tenant_ref=tenant, channel=channel, payload_hash=payload_hash)
            .first()
        )
        if duplicate:
            return _from_model(duplicate)
        current = (
            RealtimeChannelEvent.objects.select_for_update()
            .filter(tenant_ref=tenant, channel=channel)
            .aggregate(value=Max("sequence"))["value"]
            or 0
        )
        sequence = current + 1
        event_id = f"{tenant}:{channel}:{sequence}"
        try:
            row = RealtimeChannelEvent.objects.create(
                tenant_ref=tenant,
                channel=channel,
                sequence=sequence,
                event_id=event_id,
                event_type=event_type,
                source=source,
                payload=data,
                payload_hash=payload_hash,
                occurred_at=occurred,
                server_time=server_time,
            )
        except IntegrityError:
            row = RealtimeChannelEvent.objects.get(tenant_ref=tenant, channel=channel, payload_hash=payload_hash)
        _trim_history(tenant, channel)
        return _from_model(row)


def _trim_history(tenant_ref: str, channel: str) -> None:
    keep = _history_size(channel)
    overflow = list(
        RealtimeChannelEvent.objects.filter(tenant_ref=tenant_ref, channel=channel)
        .order_by("-sequence")
        .values_list("id", flat=True)[keep:]
    )
    if overflow:
        RealtimeChannelEvent.objects.filter(id__in=overflow).delete()


def _from_model(row: RealtimeChannelEvent) -> StoredRealtimeEvent:
    return StoredRealtimeEvent(
        event_id=row.event_id,
        event_type=row.event_type,
        channel=row.channel,
        sequence=row.sequence,
        source=row.source,
        occurred_at=row.occurred_at,
        server_time=row.server_time,
        data=row.payload,
    )


def snapshot(*, tenant_ref: str, channel: str) -> dict:
    latest = (
        RealtimeChannelEvent.objects.filter(tenant_ref=str(tenant_ref), channel=channel)
        .order_by("-sequence")
        .first()
    )
    pattern, entry = _channel_entry(channel)
    now = timezone.now()
    return {
        "topic": channel,
        "channel": channel,
        "channel_pattern": pattern,
        "tenant_id": str(tenant_ref),
        "as_of_sequence": latest.sequence if latest else 0,
        "as_of": (latest.server_time if latest else now).isoformat(),
        "snapshot_provider": (entry or {}).get("snapshot_provider"),
        "data": latest.payload if latest else {},
    }


def resume(*, tenant_ref: str, channel: str, after_sequence: int, limit: int = 100) -> dict:
    tenant = str(tenant_ref)
    current = (
        RealtimeChannelEvent.objects.filter(tenant_ref=tenant, channel=channel).aggregate(value=Max("sequence"))["value"]
        or 0
    )
    oldest = (
        RealtimeChannelEvent.objects.filter(tenant_ref=tenant, channel=channel).aggregate(value=Max("sequence"))["value"]
        or 0
    )
    first = RealtimeChannelEvent.objects.filter(tenant_ref=tenant, channel=channel).order_by("sequence").first()
    if first:
        oldest = first.sequence
    if current and after_sequence < oldest - 1:
        raise SnapshotRequired(current)
    rows = (
        RealtimeChannelEvent.objects.filter(tenant_ref=tenant, channel=channel, sequence__gt=after_sequence)
        .order_by("sequence")[:limit]
    )
    messages = [_from_model(row).envelope() for row in rows]
    return {
        "channel": channel,
        "messages": messages,
        "current_sequence": current,
        "resumed_from": after_sequence,
        "next_sequence": (messages[-1]["sequence"] + 1) if messages else after_sequence + 1,
        "retained_from_sequence": oldest if current else 0,
        "snapshot_required": False,
    }
