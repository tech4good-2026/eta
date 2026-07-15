from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class StoreState(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class StoreResult[T]:
    state: StoreState
    value: T | None = None


@dataclass
class _Record[T]:
    value: T | None
    expires_at: datetime


class MemoryTTLStore[T]:
    """Single-process TTL storage with value-free expiry tombstones."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._records: dict[str, _Record[T]] = {}

    def put(self, key: str, value: T, ttl_sec: int) -> None:
        self._records[key] = _Record(
            value=value,
            expires_at=self._clock() + timedelta(seconds=ttl_sec),
        )

    def get(self, key: str) -> StoreResult[T]:
        record = self._records.get(key)
        if record is None:
            return StoreResult(state=StoreState.MISSING)
        if self._clock() >= record.expires_at:
            record.value = None
            return StoreResult(state=StoreState.EXPIRED)
        return StoreResult(state=StoreState.ACTIVE, value=record.value)
