"""Unified working memory with TTL-based fact lifecycle."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StoredFact:
    """A fact stored in working memory with lifecycle metadata."""

    id: str
    data: dict[str, Any]
    timestamp: float
    ttl_ms: float


class UnifiedWorkingMemory:
    """Global working memory with TTL-based fact lifecycle management.

    Thread-safe. Facts auto-expire after ``fact_ttl_ms`` milliseconds.

    Memory watchdog (PHREAK P2.3)
    -----------------------------
    Pure stateless scoring keeps working memory near-empty (facts are passed to
    ``evaluate`` and never asserted). A climbing resident-fact count therefore
    signals an *assert-without-retract* leak: with the default 1-hour TTL such a
    leak would accumulate for the full window before becoming visible (§6). To
    surface it early, ``assert_fact`` logs a one-time WARNING the first time the
    resident fact count crosses ``high_water_mark``. Pass
    ``high_water_mark=0`` to disable the watchdog.
    """

    def __init__(
        self,
        fact_ttl_ms: float = 3_600_000,
        high_water_mark: int = 100_000,
    ) -> None:
        self._facts: dict[str, StoredFact] = {}
        self._fact_ttl_ms = fact_ttl_ms
        self._high_water_mark = max(0, high_water_mark)
        self._high_water_warned = False
        self._lock = threading.RLock()

    @property
    def facts(self) -> dict[str, StoredFact]:
        with self._lock:
            return dict(self._facts)

    @property
    def high_water_mark(self) -> int:
        """Resident-fact count above which the watchdog warns (0 = disabled)."""
        return self._high_water_mark

    def assert_fact(self, fact: dict[str, Any], fact_id: str | None = None) -> str:
        """Insert a fact, returning its unique ID."""
        with self._lock:
            fid = fact_id or str(uuid.uuid4())
            self._facts[fid] = StoredFact(
                id=fid,
                data=dict(fact),
                timestamp=time.time(),
                ttl_ms=self._fact_ttl_ms,
            )
            self._check_high_water_mark()
            return fid

    def _check_high_water_mark(self) -> None:
        """Log a one-time warning if resident facts exceed the high-water mark.

        Caller must hold ``self._lock``. Fires once until the count drops back
        to/below the mark (then re-arms), so a sustained leak warns once rather
        than on every assert.
        """
        if self._high_water_mark <= 0:
            return
        count = len(self._facts)
        if count > self._high_water_mark:
            if not self._high_water_warned:
                self._high_water_warned = True
                logger.warning(
                    "WorkingMemory high-water mark exceeded: %d facts resident "
                    "(> %d). Pure stateless scoring should keep working memory "
                    "near-empty; a climbing count signals an assert-without-"
                    "retract leak. Check that asserted facts are retracted or "
                    "that fact TTL is appropriate.",
                    count,
                    self._high_water_mark,
                )
        elif self._high_water_warned:
            # Dropped back under the mark - re-arm so a future breach warns again.
            self._high_water_warned = False

    def retract_fact(self, fact_id: str) -> bool:
        """Remove a fact. Returns True if it existed."""
        with self._lock:
            existed = self._facts.pop(fact_id, None) is not None
            if existed:
                self._check_high_water_mark()
            return existed

    def get_fact(self, fact_id: str) -> dict[str, Any] | None:
        """Get fact data by ID."""
        with self._lock:
            sf = self._facts.get(fact_id)
            return dict(sf.data) if sf else None

    def get_fact_by_id(self, fact_id: str) -> dict[str, Any] | None:
        """Alias for get_fact."""
        return self.get_fact(fact_id)

    def get_all_facts(self) -> dict[str, dict[str, Any]]:
        """Return all facts (copies)."""
        with self._lock:
            return {fid: dict(sf.data) for fid, sf in self._facts.items()}

    def cleanup_expired_facts(self) -> int:
        """Remove TTL-expired facts, return count removed."""
        with self._lock:
            now = time.time()
            expired = [
                fid for fid, sf in self._facts.items() if (now - sf.timestamp) * 1000 > sf.ttl_ms
            ]
            for fid in expired:
                del self._facts[fid]
            return len(expired)

    def clear(self) -> None:
        with self._lock:
            self._facts.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._facts)
