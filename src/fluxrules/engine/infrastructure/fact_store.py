"""Fact Lifecycle Management.

Provides a type-safe fact store with insert/update/retract semantics,
change tracking, and event notification for integration with the PHREAK
network.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FactEvent(Enum):
    """Events raised when facts change."""

    INSERTED = "inserted"
    UPDATED = "updated"
    RETRACTED = "retracted"


@dataclass(frozen=True)
class FactChange:
    """Immutable record of a fact change."""

    event: FactEvent
    key: str
    value: Any
    previous_value: Any = None
    timestamp: float = field(default_factory=time.time)


FactListener = Callable[[FactChange], None]


class FactStore:
    """Manages fact lifecycle with change tracking and event notification.

    Features:
    - Insert/update/retract with validation
    - Change history for audit
    - Listener notification on changes
    - Snapshot/restore for transactional evaluation
    - Bulk operations

    Usage:
        store = FactStore()
        store.insert("age", 30)
        store.update("age", 31)
        store.retract("age")
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._facts: dict[str, Any] = {}
        self._history: list[FactChange] = []
        self._max_history = max_history
        self._listeners: list[FactListener] = []
        self._locked_keys: set[str] = set()

    # Query

    def get(self, key: str, default: Any = None) -> Any:
        """Get a fact value by key."""
        return self._facts.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._facts[key]

    def __contains__(self, key: str) -> bool:
        return key in self._facts

    def __len__(self) -> int:
        return len(self._facts)

    def __iter__(self) -> Iterator[str]:
        return iter(self._facts)

    @property
    def facts(self) -> dict[str, Any]:
        """Return a copy of current facts."""
        return dict(self._facts)

    @property
    def history(self) -> list[FactChange]:
        """Return change history."""
        return list(self._history)

    # Mutation

    def insert(self, key: str, value: Any) -> None:
        """Insert a new fact. Raises if key already exists."""
        if key in self._facts:
            raise KeyError(f"Fact '{key}' already exists. Use update() instead.")
        self._set(key, value, FactEvent.INSERTED)

    def update(self, key: str, value: Any) -> None:
        """Update an existing fact. Raises if key doesn't exist."""
        if key not in self._facts:
            raise KeyError(f"Fact '{key}' does not exist. Use insert() instead.")
        if key in self._locked_keys:
            raise PermissionError(f"Fact '{key}' is locked and cannot be modified.")
        self._set(key, value, FactEvent.UPDATED)

    def upsert(self, key: str, value: Any) -> None:
        """Insert or update a fact."""
        if key in self._locked_keys and key in self._facts:
            raise PermissionError(f"Fact '{key}' is locked and cannot be modified.")
        event = FactEvent.UPDATED if key in self._facts else FactEvent.INSERTED
        self._set(key, value, event)

    def retract(self, key: str) -> Any:
        """Remove a fact. Returns the removed value. Raises if missing."""
        if key not in self._facts:
            raise KeyError(f"Fact '{key}' does not exist.")
        if key in self._locked_keys:
            raise PermissionError(f"Fact '{key}' is locked and cannot be retracted.")
        prev = self._facts.pop(key)
        change = FactChange(event=FactEvent.RETRACTED, key=key, value=None, previous_value=prev)
        self._record(change)
        return prev

    def bulk_insert(self, facts: dict[str, Any]) -> None:
        """Insert multiple facts atomically."""
        # Validate all first
        for key in facts:
            if key in self._facts:
                raise KeyError(f"Fact '{key}' already exists.")
        for key, value in facts.items():
            self._set(key, value, FactEvent.INSERTED)

    def clear(self) -> None:
        """Retract all facts."""
        keys = list(self._facts.keys())
        for key in keys:
            if key not in self._locked_keys:
                self.retract(key)

    # Locking

    def lock(self, key: str) -> None:
        """Lock a fact key to prevent modification."""
        self._locked_keys.add(key)

    def unlock(self, key: str) -> None:
        """Unlock a fact key."""
        self._locked_keys.discard(key)

    # Snapshots

    def snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current facts for transactional rollback."""
        return dict(self._facts)

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore facts from a snapshot (no events fired)."""
        self._facts = dict(snapshot)

    # Listeners

    def add_listener(self, listener: FactListener) -> None:
        """Register a change listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: FactListener) -> None:
        """Unregister a change listener."""
        self._listeners.remove(listener)

    # Internal

    def _set(self, key: str, value: Any, event: FactEvent) -> None:
        prev = self._facts.get(key)
        self._facts[key] = value
        change = FactChange(event=event, key=key, value=value, previous_value=prev)
        self._record(change)

    def _record(self, change: FactChange) -> None:
        self._history.append(change)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        for listener in self._listeners:
            listener(change)
