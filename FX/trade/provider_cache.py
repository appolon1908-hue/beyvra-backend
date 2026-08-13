from dataclasses import dataclass
from time import monotonic


@dataclass
class CacheEntry:
    value: object
    expires_at: float
    schema_version: str


class BoundedProviderCache:
    def __init__(self, max_entries=256):
        self.max_entries = max_entries
        self._entries = {}

    def get(self, key, schema_version="1"):
        entry = self._entries.get(key)
        if entry is None or entry.schema_version != schema_version or entry.expires_at <= monotonic():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key, value, ttl_seconds, schema_version="1"):
        if len(self._entries) >= self.max_entries and key not in self._entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = CacheEntry(value, monotonic() + ttl_seconds, schema_version)

    def clear(self):
        self._entries.clear()
