"""Missing-field semantics for ``not`` nodes.

A condition on a field that is missing from the fact evaluates to ``False``.
Under ``AND`` / ``OR`` that is harmless: a rule never fires because of a field
it could not see. Under ``NOT`` it inverts to ``True``, so
``~(F("blocked") == True)`` fires on a fact with no ``blocked`` key, and a key
sent as ``is_blocked`` silently lets the rule through.

``EngineConfig.missing_field`` chooses how a ``NOT`` treats this case:

- ``"false"``: keep the 1.x behaviour.
- ``"unknown"``: a missing field is *unknown*, with SQL NULL-style
  (Kleene) three-valued logic. ``NOT unknown`` is unknown, and a rule fires only
  when its condition is definitely ``True``.
- ``None`` (default): behave as ``"false"``, but warn once with
  :class:`~fluxrules.domain.errors.MissingFieldNotWarning` when a ``NOT`` fires
  only because a field was missing. Each ``not`` node warns at most once and
  then stops checking, so the default costs nothing after the first warning.

Only ``not`` nodes need the three-valued walk. Without negation, unknown and
``False`` lead to the same "fire / don't fire" answer, so ``AND`` / ``OR`` keep
their plain boolean fast path. And because a definite three-valued result always
equals the plain result, a ``NOT`` that evaluates to ``False`` is final in every
mode: the extra walk only runs when a ``NOT`` fires *and* one of the fields
under it is missing.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

__all__ = [
    "MISSING_FIELD_MODES",
    "NotState",
    "evaluate_tristate",
    "leaf_fields",
    "not_child",
    "resolve_not",
]

MISSING_FIELD_MODES = (None, "false", "unknown")

Tristate = bool | None
LeafFn = Callable[[dict[str, Any], dict[str, Any]], bool]
OtherFn = Callable[[dict[str, Any], dict[str, Any]], bool]


def not_child(node: dict[str, Any]) -> dict[str, Any] | None:
    """Return the single condition a ``not`` node negates.

    ``{"type": "not", "conditions": [a, b]}`` means ``not any(a, b)``, which is
    ``NOT (a OR b)``, so a list form is returned as an ``or`` node.
    """
    inner = node.get("condition") or node.get("child")
    if inner:
        return inner
    inner_list = node.get("conditions") or node.get("children") or []
    if inner_list:
        return {"type": "or", "conditions": list(inner_list)}
    return None


def leaf_fields(node: Any) -> tuple[str, ...]:
    """Field names of every ``condition`` leaf under *node*.

    ``exists`` nodes are skipped: they test presence and are never unknown.
    """
    out: list[str] = []
    _collect(node, out)
    return tuple(dict.fromkeys(out))


def _collect(node: Any, out: list[str]) -> None:
    if not isinstance(node, dict):
        return
    ctype = node.get("type")
    if ctype == "condition":
        field = node.get("field")
        if field:
            out.append(field)
        return
    if ctype in ("and", "or", "group", "composite"):
        for child in node.get("conditions") or node.get("children") or []:
            _collect(child, out)
        return
    if ctype == "not":
        _collect(not_child(node), out)


def evaluate_tristate(
    node: Any,
    facts: dict[str, Any],
    *,
    leaf: LeafFn,
    other: OtherFn,
    empty: bool,
) -> Tristate:
    """Evaluate a condition tree with Kleene logic: ``True``, ``False`` or ``None``.

    Args:
        node: the condition tree.
        facts: the flat fact dict.
        leaf: evaluates a ``condition`` leaf whose field is present.
        other: evaluates node types this walk does not model (``accumulate``,
            unknown types), returning a plain bool.
        empty: the value of an empty ``and`` group or an empty ``not``. Each
            evaluator passes its own, so this walk agrees with it exactly.
    """
    if not isinstance(node, dict):
        return False
    ctype = node.get("type")

    if ctype == "condition":
        field = node.get("field", "")
        if field not in facts:
            from fluxrules.domain.errors import FieldNotFoundError, is_field_typo

            if is_field_typo(field, facts):
                raise FieldNotFoundError.for_field(field, facts)
            return None
        return leaf(node, facts)

    if ctype in ("and", "or", "group", "composite"):
        if ctype == "and":
            logic = "AND"
        elif ctype == "or":
            logic = "OR"
        else:
            logic = str(node.get("logic") or node.get("op") or "AND").upper()
        children = node.get("conditions") or node.get("children") or []
        if logic == "AND":
            if not children:
                return empty
            result: Tristate = True
            for child in children:
                value = evaluate_tristate(child, facts, leaf=leaf, other=other, empty=empty)
                if value is False:
                    return False
                if value is None:
                    result = None
            return result
        result = False
        for child in children:
            value = evaluate_tristate(child, facts, leaf=leaf, other=other, empty=empty)
            if value is True:
                return True
            if value is None:
                result = None
        return result

    if ctype == "not":
        inner = not_child(node)
        if inner is None:
            return empty
        value = evaluate_tristate(inner, facts, leaf=leaf, other=other, empty=empty)
        return None if value is None else not value

    if ctype == "exists":
        field = node.get("field")
        if field:
            return field in facts and facts[field] is not None
        inner = node.get("condition")
        if inner is None:
            return False
        return evaluate_tristate(inner, facts, leaf=leaf, other=other, empty=empty)

    return other(node, facts)


class NotState:
    """Per-``not``-node data, computed once so the hot path does no tree walks.

    Attributes:
        child: the negated condition (see :func:`not_child`).
        fields: :func:`leaf_fields` of *child*.
        single_leaf: *child* is a single ``condition`` leaf.
        warned: set once this node has emitted its warning; in the default mode
            the node then costs nothing more.
    """

    __slots__ = ("child", "fields", "single_leaf", "warned")

    def __init__(self, node: dict[str, Any]) -> None:
        self.child = not_child(node)
        self.fields = leaf_fields(self.child) if self.child is not None else ()
        # ``~(F("x") == 1)``: the child is one leaf, so a missing field means
        # unknown without walking anything.
        self.single_leaf = self.child is not None and self.child.get("type") == "condition"
        self.warned = False


def resolve_not(
    state: NotState,
    plain: bool,
    facts: dict[str, Any],
    mode: str | None,
    *,
    leaf: LeafFn,
    other: OtherFn,
    empty: bool,
) -> bool:
    """Final value of a ``not`` node, given its plain two-valued result.

    Args:
        state: the node's :class:`NotState`.
        plain: the ``not`` node's result under the 1.x rule (missing = ``False``).
        facts: the flat fact dict.
        mode: ``EngineConfig.missing_field``.
        leaf, other, empty: forwarded to :func:`evaluate_tristate`.
    """
    if not plain or mode == "false" or not state.fields:
        return plain
    if mode is None and state.warned:
        return plain
    fields = state.fields
    for f in fields:
        if f not in facts:
            break
    else:
        return plain
    if state.single_leaf:
        value: Tristate = None
    else:
        value = evaluate_tristate(state.child, facts, leaf=leaf, other=other, empty=empty)
    if mode == "unknown":
        return value is False
    if value is None:
        from fluxrules.domain.errors import MissingFieldNotWarning

        state.warned = True
        missing = [f for f in fields if f not in facts]
        warnings.warn(
            f"A NOT condition fired only because field(s) {missing} were missing from "
            "the fact. From fluxrules 2.0 this NOT will not fire. Set "
            "EngineConfig(missing_field='unknown') to adopt the new behaviour now, or "
            "missing_field='false' to keep the current one and silence this warning; "
            "use ~F(...).exists() to test for absence explicitly.",
            MissingFieldNotWarning,
            stacklevel=2,
        )
    return plain
