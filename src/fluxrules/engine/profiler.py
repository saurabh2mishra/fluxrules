"""Rule execution profiler.

Measures wall-clock time for individual rule evaluations so that
hot-spots can be identified and optimised.

Example::

    >>> profiler = RuleProfiler()
    >>> profiler.start(1)
    >>> profiler.end(1)  # returns elapsed seconds
    0.00012...
"""

from __future__ import annotations

import time
from typing import Any


class RuleProfiler:
    """Collect per-rule timing data.

    Not thread-safe - each thread / task should use its own instance.
    """

    def __init__(self) -> None:
        self.timings: dict[int, dict[str, Any]] = {}

    def start(self, rule_id: int) -> None:
        """Record the start time for *rule_id*.

        Args:
            rule_id: Numeric identifier of the rule being evaluated.
        """
        self.timings[rule_id] = {"start": time.time()}

    def end(self, rule_id: int) -> float:
        """Record the end time and return elapsed seconds.

        Args:
            rule_id: Numeric identifier of the rule.

        Returns:
            Elapsed wall-clock seconds, or ``0`` if *start* was never called.
        """
        if rule_id in self.timings and "start" in self.timings[rule_id]:
            elapsed: float = time.time() - self.timings[rule_id]["start"]
            self.timings[rule_id]["elapsed"] = elapsed
            return elapsed
        return 0.0

    def get_stats(self) -> dict[int, float]:
        """Return a mapping of rule_id → elapsed seconds.

        Returns:
            Dictionary keyed by rule id with elapsed time values.
        """
        return {rule_id: data.get("elapsed", 0.0) for rule_id, data in self.timings.items()}

    def reset(self) -> None:
        """Clear all recorded timings."""
        self.timings = {}
