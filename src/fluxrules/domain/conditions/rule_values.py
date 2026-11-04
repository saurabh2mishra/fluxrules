"""Find rule values that do not suit their operator.

``F("amount") > None`` and a ``regex`` that does not compile can never match.
``F("code").starts_with(75)`` does match, but only because ``starts_with``
reads ``75`` as the text ``"75"``, which the rule does not say. :func:`value_problems`
lists such conditions, and :func:`warn_value_problems` warns the author with
:class:`~fluxrules.domain.errors.RuleValueWarning` when the rule is created.
The rule still loads and evaluates as before.
"""

from __future__ import annotations

import datetime as dt
import re
import threading
import warnings
from decimal import Decimal
from typing import Any

from fluxrules.domain.errors import RuleValueWarning
from fluxrules.engine.operators import (
    CASE_INSENSITIVE_OPS,
    ORDERING_OPS,
    approx_parts,
    is_membership_collection,
    is_nan,
)
from fluxrules.utils.warn import caller_stacklevel

__all__ = ["reset_value_warnings", "value_problems", "warn_value_problems"]

_ALIASES = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_TEXT_OPS = frozenset({"starts_with", "ends_with"})
# What ``>`` and the like can order: numbers, text, dates and times.
_ORDERABLE = (int, float, Decimal, str, dt.date, dt.time, dt.timedelta)

# Each problem warns once per process: a rule is rebuilt internally (copied,
# stored, sent to worker processes), and its author needs to hear it once.
_warned: set[str] = set()
_lock = threading.Lock()


def describe_value(value: Any) -> str:
    """*value* and its kind, for a message: ``the text '5'``, ``the boolean True``."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return f"the boolean {value!r}"
    if isinstance(value, str):
        return f"the text {value!r}"
    if isinstance(value, (int, float, Decimal)):
        return f"the number {value!r}" if not isinstance(value, Decimal) else f"the number {value}"
    kinds: dict[type, str] = {list: "a list", tuple: "a tuple", dict: "a mapping", set: "a set"}
    kind = kinds.get(type(value))
    if kind is None:
        name = type(value).__name__
        kind = f"an {name}" if name[:1] in "aeiou" else f"a {name}"
    return f"{value!r} ({kind})"


# Marks a problem whose condition still matches some facts (a value read as
# text, or one bad member of a list), so its message does not end with
# "The condition can never match."
_READ_AS_TEXT = "still matches"


def _problem(op: str, value: Any) -> str | None:
    """Why *value* does not suit *op*, or ``None`` when it does.

    A message starting with :data:`_READ_AS_TEXT` describes a value that is
    converted, not one that can never match.
    """
    op = _ALIASES.get(op, op)
    if op in ORDERING_OPS:
        if isinstance(value, bool) or not isinstance(value, _ORDERABLE):
            return f"'{op}' needs a number, text, a date or a time, but got {describe_value(value)}"
        if is_nan(value):
            return f"'{op}' cannot order anything against NaN"
        return None
    if op in _TEXT_OPS:
        if not isinstance(value, str):
            return _read_as_text(op, value)
        return None
    if op == "approx":
        target = approx_parts(value)[0]
        if isinstance(target, bool) or not isinstance(target, (int, float, Decimal)):
            return f"'approx' needs a number, but got {describe_value(target)}"
        if is_nan(target):
            return "'approx' cannot match NaN"
        return None
    if op == "in_ignore_case":
        members = value if is_membership_collection(value) else (value,)
        others = [m for m in members if not isinstance(m, str)]
        if not others:
            return None
        problem = f"'in_ignore_case' compares text, but got {describe_value(others[0])}"
        if len(others) < len(members):
            # The text members still match; only this one never does.
            return f"{_READ_AS_TEXT}{problem}, which never matches. Write it as text or remove it"
        return problem
    if op in CASE_INSENSITIVE_OPS:
        if not isinstance(value, str):
            return f"'{op}' needs text, but got {describe_value(value)}"
        return None
    if op == "regex":
        if not isinstance(value, str):
            return _read_as_text(op, value)
        try:
            re.compile(value)
        except re.error as exc:
            return f"the pattern {value!r} does not compile: {exc}"
    return None


def _read_as_text(op: str, value: Any) -> str:
    """``starts_with``, ``ends_with`` and ``regex`` compare ``str()`` of both sides."""
    text = str(value)
    return (
        f"{_READ_AS_TEXT}'{op}' compares text, so {describe_value(value)} is read as "
        f'the text "{text}". Write "{text}" to say so'
    )


def value_problems(tree: Any, *, path: str = "root") -> list[str]:
    """Every condition in *tree* whose value does not suit its operator.

    Each entry is one sentence naming the condition and the problem. Malformed
    trees are skipped for the validator to report.
    """
    out: list[str] = []
    _collect(tree, path, out)
    return out


def _collect(tree: Any, path: str, out: list[str]) -> None:
    if isinstance(tree, list):
        for i, item in enumerate(tree):
            _collect(item, f"{path}[{i}]", out)
        return
    if not isinstance(tree, dict):
        return
    if tree.get("type") == "condition":
        op = tree.get("op")
        if isinstance(op, str) and "value" in tree:
            problem = _problem(op, tree["value"])
            if problem is not None:
                where = f" at {path!r}" if path != "root" else ""
                if problem.startswith(_READ_AS_TEXT):
                    problem = problem[len(_READ_AS_TEXT) :]
                    ending = ""
                else:
                    ending = " The condition can never match."
                out.append(f"Condition{where} on field {tree.get('field')!r}: {problem}.{ending}")
        return
    for key, child in tree.items():
        if isinstance(child, (dict, list)):
            _collect(child, f"{path}.{key}", out)


def warn_value_problems(tree: Any) -> None:
    """Warn once per process for each problem :func:`value_problems` finds."""
    for message in value_problems(tree):
        with _lock:
            if message in _warned:
                continue
            _warned.add(message)
        warnings.warn(message, RuleValueWarning, stacklevel=caller_stacklevel())


def reset_value_warnings() -> None:
    """Forget which problems have warned, so each warns again (for tests)."""
    with _lock:
        _warned.clear()
