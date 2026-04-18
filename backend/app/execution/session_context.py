from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from app.execution.agenda import Agenda
from app.execution.working_memory import WorkingMemory


@dataclass
class AssertResult:
    fact_id: str
    asserted: bool
    was_update: bool
    evicted_fact_ids: list[str] = field(default_factory=list)
    facts_count: int = 0
    memory_bytes: int = 0
    message: str | None = None


@dataclass
class RetractResult:
    fact_id: str
    retracted: bool
    facts_count: int
    memory_bytes: int


@dataclass
class SessionStats:
    session_id: str
    group: str
    created_at: datetime
    expires_at: datetime
    ttl_seconds: int
    is_expired: bool
    destroyed: bool
    facts_count: int
    memory_bytes: int
    max_facts: int
    memory_budget_bytes: int
    agenda_size: int


@dataclass
class SessionContext:
    session_id: str
    group: str
    created_at: datetime
    ttl_seconds: int
    working_memory: WorkingMemory = field(default_factory=WorkingMemory)
    rete_network: Any = None
    agenda: Agenda = field(default_factory=Agenda)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        self._destroyed = False
        self._fact_sizes: dict[str, int] = {
            fact_id: self._estimate_fact_size(record.payload)
            for fact_id, record in self.working_memory.facts().items()
        }

    def assert_fact(self, fact_id: str, event: dict[str, Any]) -> AssertResult:
        self._assert_active()

        evicted_fact_ids: list[str] = []
        max_facts = int(self.config.get("max_facts", 10_000))
        memory_budget = int(self.config.get("memory_budget_bytes", 5_000_000))

        was_update = fact_id in self.working_memory.facts()

        if max_facts <= 0:
            if was_update:
                self.retract_fact(fact_id)
                evicted_fact_ids.append(fact_id)
            return AssertResult(
                fact_id=fact_id,
                asserted=False,
                was_update=was_update,
                evicted_fact_ids=evicted_fact_ids,
                facts_count=len(self.working_memory.facts()),
                memory_bytes=self._current_memory_bytes(),
                message="Session max_facts is 0; fact retention is disabled",
            )

        if not was_update:
            while len(self.working_memory.facts()) >= max_facts:
                evicted = self._evict_oldest_fact()
                if evicted is None:
                    break
                evicted_fact_ids.append(evicted)

        self.working_memory.update_fact(fact_id, event)
        self._fact_sizes[fact_id] = self._estimate_fact_size(event)

        while self._current_memory_bytes() > memory_budget and self.working_memory.facts():
            evicted = self._evict_oldest_fact()
            if evicted is None:
                break
            evicted_fact_ids.append(evicted)

        asserted = fact_id in self.working_memory.facts()
        message: str | None = None
        if not asserted:
            message = "Fact was evicted to satisfy session memory constraints"

        return AssertResult(
            fact_id=fact_id,
            asserted=asserted,
            was_update=was_update,
            evicted_fact_ids=evicted_fact_ids,
            facts_count=len(self.working_memory.facts()),
            memory_bytes=self._current_memory_bytes(),
            message=message,
        )

    def retract_fact(self, fact_id: str) -> RetractResult:
        self._assert_active()

        existing_record = self.working_memory.facts().get(fact_id)
        existing_payload = dict(existing_record.payload) if existing_record is not None else {}
        retracted = self.working_memory.retract_fact(fact_id)
        self._fact_sizes.pop(fact_id, None)

        if hasattr(self.agenda, "retract_fact_activations"):
            self.agenda.retract_fact_activations(fact_id)

        self._notify_rete_retract(fact_id, existing_payload)

        return RetractResult(
            fact_id=fact_id,
            retracted=retracted,
            facts_count=len(self.working_memory.facts()),
            memory_bytes=self._current_memory_bytes(),
        )

    def get_stats(self) -> SessionStats:
        expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)
        return SessionStats(
            session_id=self.session_id,
            group=self.group,
            created_at=self.created_at,
            expires_at=expires_at,
            ttl_seconds=self.ttl_seconds,
            is_expired=self.is_expired(),
            destroyed=self._destroyed,
            facts_count=len(self.working_memory.facts()),
            memory_bytes=self._current_memory_bytes(),
            max_facts=int(self.config.get("max_facts", 10_000)),
            memory_budget_bytes=int(self.config.get("memory_budget_bytes", 5_000_000)),
            agenda_size=len(self.agenda),
        )

    def is_expired(self) -> bool:
        expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)
        return datetime.now(timezone.utc) >= expires_at

    def destroy(self) -> None:
        if self._destroyed:
            return

        for fact_id in list(self.working_memory.facts().keys()):
            self.retract_fact(fact_id)

        if hasattr(self.agenda, "clear"):
            self.agenda.clear()

        self._notify_rete_destroy()
        self._destroyed = True

    def _evict_oldest_fact(self) -> str | None:
        facts = self.working_memory.facts()
        if not facts:
            return None

        oldest = min(facts.values(), key=lambda record: record.revision)
        self.retract_fact(oldest.fact_id)
        return oldest.fact_id

    def _notify_rete_retract(self, fact_id: str, payload: dict[str, Any]) -> None:
        if self.rete_network is None:
            return

        for method_name in ("retract_fact", "remove_fact", "remove_event"):
            method = getattr(self.rete_network, method_name, None)
            if callable(method):
                try:
                    method(fact_id, payload)
                except TypeError:
                    method(fact_id)
                return

    def _notify_rete_destroy(self) -> None:
        if self.rete_network is None:
            return

        for method_name in ("clear", "reset"):
            method = getattr(self.rete_network, method_name, None)
            if callable(method):
                method()
                return

    def _current_memory_bytes(self) -> int:
        return sum(self._fact_sizes.values())

    @staticmethod
    def _estimate_fact_size(event: dict[str, Any]) -> int:
        return len(json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    def _assert_active(self) -> None:
        if self._destroyed:
            raise RuntimeError(f"Session '{self.session_id}' has been destroyed")
