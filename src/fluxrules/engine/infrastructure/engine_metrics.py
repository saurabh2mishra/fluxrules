"""Low-overhead operational metrics for the engine (PHREAK P2.4).

These are *advisory* counters maintained on (or alongside) the hot path so an
operator can *see* the failure modes the trustworthiness analysis warned about
- a hot field defeating the alpha filter, a leaf-memo collapse, a rebuild storm,
or a working-memory leak - without attaching a profiler.

Design principles:
- **Increment-only on the hot path; ratios computed on read.** No locks on the
  counters: under the P0.2 shared-engine contract an increment may race and be
  lost, but the numbers never affect ``fired_rules`` - they are observability,
  not control.
- **Flag-gated.** The engine only instantiates :class:`EngineMetrics` when
  ``enable_metrics=True``, so the default path pays nothing.
- **Bounded.** Latency samples live in a fixed-size ring buffer, so memory is
  O(window) regardless of traffic.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any


class LatencyReservoir:
    """Fixed-size ring buffer of recent latencies with nearest-rank percentiles.

    Bounded at ``window`` samples (default 2048): O(window) memory, O(1) record,
    O(window log window) on a percentile read (sort a snapshot). Suitable for
    per-request SLO tracking where only recent behavior matters.
    """

    __slots__ = ("_count", "_samples")

    def __init__(self, window: int = 2048) -> None:
        self._samples: deque[float] = deque(maxlen=max(1, window))
        self._count = 0

    def record(self, value_ms: float) -> None:
        self._samples.append(value_ms)
        self._count += 1

    @property
    def count(self) -> int:
        """Total samples recorded (not just those resident in the window)."""
        return self._count

    def percentiles(self, pcts: tuple[float, ...] = (50.0, 95.0, 99.0)) -> dict[str, float]:
        snapshot = sorted(self._samples)
        out: dict[str, float] = {}
        n = len(snapshot)
        for pct in pcts:
            key = f"p{int(pct)}"
            if n == 0:
                out[key] = 0.0
                continue
            rank = math.ceil(pct / 100.0 * n)
            idx = min(max(rank, 1), n) - 1
            out[key] = snapshot[idx]
        return out

    def reset(self) -> None:
        self._samples.clear()
        self._count = 0


class EngineMetrics:
    """Operational counters for a single engine instance (P2.4).

    Tracks the signals the API stats endpoint surfaces:
    - leaf-memo hit/miss (cross-rule leaf sharing effectiveness),
    - per-fact linked-rule count (sanity vs the alpha candidate count),
    - per-fact eval latency (p50/p95/p99) when fed by the caller.

    Alpha prune ratio, node-memory hit rate, and working-memory size are owned by
    their respective components (``_AlphaStats``, ``NodeMemory.stats``,
    ``UnifiedWorkingMemory``) and merged by ``get_observability_metrics`` - they
    are not duplicated here.
    """

    __slots__ = (
        "facts",
        "latency",
        "leaf_hits",
        "leaf_misses",
        "linked_rules_last",
        "linked_rules_total",
    )

    def __init__(self, latency_window: int = 2048) -> None:
        self.leaf_hits = 0
        self.leaf_misses = 0
        self.linked_rules_total = 0
        self.linked_rules_last = 0
        self.facts = 0
        self.latency = LatencyReservoir(window=latency_window)

    # Hot-path recorders (increment-only)

    def record_leaf(self, *, hit: bool) -> None:
        if hit:
            self.leaf_hits += 1
        else:
            self.leaf_misses += 1

    def record_linked(self, count: int) -> None:
        self.facts += 1
        self.linked_rules_total += count
        self.linked_rules_last = count

    def record_latency_ms(self, latency_ms: float) -> None:
        self.latency.record(latency_ms)

    # Read-time derivations

    @property
    def leaf_memo_hit_rate(self) -> float:
        total = self.leaf_hits + self.leaf_misses
        return self.leaf_hits / total if total else 0.0

    @property
    def avg_linked_rules(self) -> float:
        return self.linked_rules_total / self.facts if self.facts else 0.0

    def as_dict(self) -> dict[str, Any]:
        pcts = self.latency.percentiles()
        return {
            "leaf_memo_hits": self.leaf_hits,
            "leaf_memo_misses": self.leaf_misses,
            "leaf_memo_hit_rate": self.leaf_memo_hit_rate,
            "linked_rules_last": self.linked_rules_last,
            "linked_rules_avg": self.avg_linked_rules,
            "eval_latency_ms_p50": pcts["p50"],
            "eval_latency_ms_p95": pcts["p95"],
            "eval_latency_ms_p99": pcts["p99"],
            "eval_latency_samples": self.latency.count,
        }

    def reset(self) -> None:
        self.leaf_hits = 0
        self.leaf_misses = 0
        self.linked_rules_total = 0
        self.linked_rules_last = 0
        self.facts = 0
        self.latency.reset()
