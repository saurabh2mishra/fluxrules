"""Report comparisons that cannot be made.

:func:`fluxrules.engine.operators.compare_operator` returns an
:class:`Uncomparable` (a falsy value) for a comparison with no answer, such as
``"abc" > 5`` or ``None > 5``, and counts it (see :func:`events`). Once per
rule, :func:`fluxrules.domain.conditions.uncomparable_rules.settle` passes each
:class:`~fluxrules.domain.comparison_issues.ComparisonIssue` that leaves the
rule undecided to :func:`report`. What happens next depends on
``EngineConfig.uncomparable``:

- ``None`` (default): the condition is no match, and a
  :class:`~fluxrules.domain.errors.ComparisonWarning` is emitted once per
  process for each field, operator and pair of types.
- ``"false"``: no match, silently.
- ``"unknown"``: the comparison is unknown, so a rule fires only when its
  condition is definitely true: ``NOT`` over it does not fire.
- ``"raise"``: :class:`~fluxrules.domain.errors.UncomparableValuesError`.

In every mode the issue is also listed in the evaluation's
``comparison_issues``. An evaluation opens a :func:`comparison_scope` with its
engine's mode; a comparison made outside any scope (a custom engine calling
``evaluate_conditions`` directly, for example) uses the process-wide config.

Nothing here runs for a comparison that has an answer, so the normal path
costs nothing extra.
"""

from __future__ import annotations

import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fluxrules.domain.comparison_issues import ComparisonIssue

__all__ = [
    "UNCOMPARABLE_MODES",
    "ComparisonScope",
    "Uncomparable",
    "comparison_scope",
    "events",
    "note",
    "report",
]

UNCOMPARABLE_MODES = (None, "false", "unknown", "raise")


class Uncomparable:
    """The result of a comparison that could not be made. It is falsy."""

    __slots__ = ("issue",)

    def __init__(self, issue: ComparisonIssue) -> None:
        self.issue = issue

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"Uncomparable({self.issue!r})"


class ComparisonScope:
    """The issues one evaluation found, and the mode that evaluation runs under."""

    __slots__ = ("issues", "mode", "_lock", "_seen")

    def __init__(self, mode: str | None) -> None:
        self.mode = mode
        self.issues: list[ComparisonIssue] = []
        self._seen: set[ComparisonIssue] = set()
        # The engine's opt-in thread pool can add from several threads.
        self._lock = threading.Lock()

    def add(self, issue: ComparisonIssue) -> None:
        with self._lock:
            if issue not in self._seen:
                self._seen.add(issue)
                self.issues.append(issue)


_scope: ContextVar[ComparisonScope | None] = ContextVar("fluxrules_comparison_scope", default=None)

# Counts every comparison that could not be made. A rule's evaluation reads it
# before and after: only if it moved does the rule need settling. Only a
# trigger for extra work, so a race between threads costs at most one extra
# walk, never a wrong answer.
_events = 0

# Issues already warned about in this process.
_warned: set[ComparisonIssue] = set()


def events() -> int:
    """How many comparisons this process could not make so far."""
    return _events


def note() -> None:
    """Count one comparison that could not be made."""
    global _events
    _events += 1


@contextmanager
def comparison_scope(mode: str | None) -> Iterator[ComparisonScope]:
    """Collect the issues of one evaluation, under *mode*.

    Nested scopes are independent: an evaluation inside another one (a rule
    action that evaluates rules, for example) lists its own issues.
    """
    scope = ComparisonScope(mode)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


def current_mode() -> str | None:
    """The mode of the open scope, or else of the process-wide config."""
    scope = _scope.get()
    if scope is not None:
        return scope.mode
    from fluxrules.engine.configuration import get_config

    return get_config().uncomparable


def report(issue: ComparisonIssue) -> None:
    """Record, warn about or raise for *issue*, as the current mode says."""
    scope = _scope.get()
    if scope is not None:
        scope.add(issue)
        mode = scope.mode
    else:
        from fluxrules.engine.configuration import get_config

        mode = get_config().uncomparable
    if mode == "raise":
        from fluxrules.domain.errors import UncomparableValuesError

        raise UncomparableValuesError(issue)
    if mode is None and issue not in _warned:
        _warned.add(issue)
        warn(issue)


def warn(issue: ComparisonIssue) -> None:
    """Emit the :class:`ComparisonWarning` for *issue*."""
    from fluxrules.domain.errors import ComparisonWarning
    from fluxrules.utils.warn import caller_stacklevel

    warnings.warn(
        f"{issue.describe()} The condition is no match, and NOT over it fires. Set "
        "EngineConfig(uncomparable='unknown') so NOT over it does not fire, 'raise' "
        "to raise an error, or 'false' to silence this warning.",
        ComparisonWarning,
        stacklevel=caller_stacklevel(),
    )


def warn_once(issue: ComparisonIssue) -> None:
    """Warn about *issue* unless this process already has.

    Used to repeat, in the parent process, the warnings for issues that
    ``evaluate_batch`` worker processes found.
    """
    if issue not in _warned:
        _warned.add(issue)
        warn(issue)


def reset_warnings() -> None:
    """Forget which issues were warned about, so each warns again (for tests)."""
    _warned.clear()
