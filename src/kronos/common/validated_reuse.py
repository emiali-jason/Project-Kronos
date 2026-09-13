"""Bounded process-local reuse of validation of exact, freshly read bytes.

No file metadata, mutable projection, or persisted cache is an authority.
Callers own reads, no-follow safety, domain/version tokens and identity checks.
"""
from collections import OrderedDict
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from threading import RLock


def _immutable(value):
    if value is None or type(value) in (str, bytes, int, float, bool, Decimal, date, datetime):
        return True
    if isinstance(value, Enum):
        return True
    if type(value) is tuple:
        return all(_immutable(item) for item in value)
    return (is_dataclass(value) and not isinstance(value, type)
            and value.__dataclass_params__.frozen
            and all(_immutable(getattr(value, field.name)) for field in fields(value)))


class ValidatedBytesReuse:
    """LRU bounded by entry count AND retained input bytes; failures never cached.

    Identical concurrent work coalesces under a striped lock. The LRU lock is
    held only for lookup/accounting, never I/O or validation. Mutable results
    bypass retention. Restart discards every entry. A token must cover all
    external schema/policy dependencies of the supplied pure validator.
    """
    def __init__(self, *, max_entries=32768, max_bytes=64 * 1024 * 1024):
        self._entries = OrderedDict()
        self._bytes = 0
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._lock = RLock()
        self._stripes = tuple(RLock() for _ in range(32))

    def load(self, path, encoded, token, validate):
        key = (str(path), token, validate, sha256(encoded).digest())
        with self._stripes[hash(key) % len(self._stripes)]:
            with self._lock:
                previous = self._entries.get(key)
                if previous is not None and previous[0] == encoded:
                    self._entries.move_to_end(key)
                    return previous[1]
            value = validate(encoded)
            if not _immutable(value) or len(encoded) > self._max_bytes:
                return value
            with self._lock:
                previous = self._entries.pop(key, None)
                if previous is not None:
                    self._bytes -= len(previous[0])
                self._entries[key] = (encoded, value)
                self._bytes += len(encoded)
                while (len(self._entries) > self._max_entries
                       or self._bytes > self._max_bytes):
                    _, removed = self._entries.popitem(last=False)
                    self._bytes -= len(removed[0])
            return value
