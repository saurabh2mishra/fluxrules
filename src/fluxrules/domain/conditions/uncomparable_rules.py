"""Which comparisons that cannot be made matter to a rule, and what they do.

A comparison with no answer (``"abc" > 5``, ``None > 5``) is *unknown*. Under
three-valued (Kleene) logic an unknown can still leave a rule decided:
``AND(False, unknown)`` is ``False`` and ``OR(True, unknown)`` is ``True``. Only
an unknown that leaves the rule's whole condition undecided is reported, so
the answer does not depend on which comparisons an evaluation path happened to
try first or skip: the engine stops an ``AND`` at its first false child, the
alpha prefilter skips rules, and ``fluxrules.evaluate()`` tries every child,
but they all compute the same three-valued value.

For that decision a missing field is treated exactly as the normal two-valued
evaluation treats it: no match, and with ``missing_field="unknown"`` a ``NOT``
over it does not fire. Only an unmade comparison is unknown. So wherever an
evaluation path stops early, at a definite ``False`` in an ``AND`` or a
definite ``True`` in an ``OR``, this walk agrees the group was already
decided, and every path reports the same issues. With
``uncomparable="unknown"``, whether the rule fires is then decided by full
three-valued logic, with ``missing_field="unknown"`` making a missing field
unknown too.

:func:`settle` runs once per rule, and only when a comparison under it could
not be made (see :func:`fluxrules.engine.uncomparable.events`), so a rule whose
comparisons all have answers costs nothing extra.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fluxrules.domain.comparison_issues import ComparisonIssue
from fluxrules.domain.conditions.missing_fields import evaluate_tristate, leaf_fields, not_child
from fluxrules.engine.uncomparable import Uncomparable, report

__all__ = ["evaluate_with_issues", "settle"]

Tristate = bool | None
# A leaf returns True, False or an Uncomparable (falsy).
LeafFn = Callable[[dict[str, Any], dict[str, Any]], Any]
OtherFn = Callable[[dict[str, Any], dict[str, Any]], Any]


def evaluate_with_issues(
    node: Any,
    facts: dict[str, Any],
    *,
    leaf: LeafFn,
    other: OtherFn,
    empty: bool,
    missing_unknown: bool,
    resolve_missing_not: bool = False,
) -> tuple[Tristate, list[ComparisonIssue]]:
    """Kleene value of *node*, and the issues that leave it undecided.

    A leaf whose comparison cannot be made is unknown and carries its issue.
    A missing field is unknown when *missing_unknown*, else ``False``. When the
    value is ``True`` or ``False`` the list is empty: nothing undecided it.

    Args:
        node: the condition tree.
        facts: the flat fact dict.
        leaf: evaluates a ``condition`` leaf whose field is present.
        other: evaluates node types this walk does not model (``accumulate``,
            unknown types), returning a plain bool.
        empty: the value of an empty ``and`` group or an empty ``not``, as the
            calling evaluator defines it.
        missing_unknown: a missing field is unknown (else ``False``).
        resolve_missing_not: with *missing_unknown* off, apply
            ``missing_field="unknown"`` to ``NOT`` as the two-valued evaluation
            does: a ``NOT`` that fires only because a field under it is missing
            does not fire.
    """
    if not isinstance(node, dict):
        return False, []
    ctype = node.get("type")
    kwargs: dict[str, Any] = {
        "leaf": leaf,
        "other": other,
        "empty": empty,
        "missing_unknown": missing_unknown,
        "resolve_missing_not": resolve_missing_not,
    }

    if ctype == "condition":
        if node.get("field", "") not in facts:
            return (None if missing_unknown else False), []
        result = leaf(node, facts)
        if result.__class__ is Uncomparable:
            return None, [result.issue]
        return bool(result), []

    if ctype in ("and", "or", "group", "composite"):
        if ctype == "and":
            logic = "AND"
        elif ctype == "or":
            logic = "OR"
        else:
            logic = str(node.get("logic") or node.get("op") or "AND").upper()
        children = node.get("conditions") or node.get("children") or []
        decisive = logic != "AND"  # the child value that decides the group
        if logic == "AND" and not children:
            return empty, []
        unknown: list[ComparisonIssue] | None = None
        for child in children:
            value, issues = evaluate_with_issues(child, facts, **kwargs)
            if value is decisive:
                return decisive, []
            if value is None:
                unknown = (unknown or []) + issues
        if unknown is not None:
            return None, unknown
        return not decisive, []

    if ctype == "not":
        inner = not_child(node)
        if inner is None:
            return empty, []
        value, issues = evaluate_with_issues(inner, facts, **kwargs)
        if value is None:
            return None, issues
        if value or not resolve_missing_not:
            return not value, []
        # The NOT fires. As resolve_not does under missing_field="unknown", it
        # does not if a missing field under it leaves its child undecided.
        if any(f not in facts for f in leaf_fields(inner)):
            missing = evaluate_tristate(inner, facts, leaf=leaf, other=other, empty=empty)
            if missing is not False:
                return False, []
        return True, []

    if ctype == "exists":
        field = node.get("field")
        if field:
            return field in facts and facts[field] is not None, []
        inner = node.get("condition")
        if inner is None:
            return False, []
        return evaluate_with_issues(inner, facts, **kwargs)

    return bool(other(node, facts)), []


def settle(
    root: Any,
    facts: dict[str, Any],
    plain: bool,
    *,
    leaf: LeafFn,
    other: OtherFn,
    empty: bool,
    missing_field: str | None,
    mode: str | None,
) -> bool:
    """A rule's final answer, after a comparison under it could not be made.

    Reports (lists, warns about or raises for) each issue that leaves the rule
    undecided. With ``uncomparable="unknown"`` the rule fires only when its
    condition is definitely ``True``; otherwise *plain*, its two-valued
    answer, stands.

    Args:
        root: the rule's condition tree.
        facts: the flat fact dict.
        plain: the rule's answer with every unmade comparison as ``False``.
        leaf, other, empty: as for :func:`evaluate_with_issues`.
        missing_field: ``EngineConfig.missing_field``.
        mode: ``EngineConfig.uncomparable``.
    """
    walk: dict[str, Any] = {"leaf": leaf, "other": other, "empty": empty}
    value, issues = evaluate_with_issues(
        root,
        facts,
        missing_unknown=False,
        resolve_missing_not=missing_field == "unknown",
        **walk,
    )
    if value is None:
        for issue in issues:
            report(issue)
    if mode != "unknown":
        return bool(plain)
    if missing_field == "unknown":
        value, _ = evaluate_with_issues(root, facts, missing_unknown=True, **walk)
    return value is True
