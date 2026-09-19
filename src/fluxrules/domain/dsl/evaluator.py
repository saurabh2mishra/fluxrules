"""Dependency-free evaluation of a ``condition_dsl`` tree.

``condition_dsl`` is the canonical representation of rule logic. Anything that
decides whether a rule matches must read it, rather than the flat
``conditions`` tuple, which cannot express ``OR``, ``NOT`` or nesting.

This module exists so that callers outside the PHREAK engine - notably
the REST evaluation route - can honour the full tree without reimplementing the
walk or silently degrading to a flat conjunction.

The node types accepted here match those the engine evaluates: ``condition``,
``and`` / ``or`` / ``group`` / ``composite``, ``not`` and ``exists``. Nodes that
require engine state (``accumulate``, ``sequence``, cross-fact joins) are not
supported and raise, because quietly returning ``False`` for them would be a
wrong answer dressed up as a non-match.
"""

from __future__ import annotations

from typing import Any

from fluxrules.domain.errors import LossyConditionRebuildError
from fluxrules.domain.predicates import evaluate_operator

__all__ = [
    "LossyConditionRebuildError",
    "UnsupportedDSLNodeError",
    "conditions_to_dsl",
    "evaluate_dsl",
    "has_logic",
]

_STATEFUL_NODES = frozenset({"accumulate", "sequence", "join", "cross_fact_join"})


def conditions_to_dsl(conditions) -> dict:
    """Build a DSL tree from a flat sequence of ``RuleCondition``.

    The single place that converts parsed conditions into the canonical DSL
    shape. Several call sites used to hand-roll a list of
    ``{fact, operator, value}`` dicts instead, which meant the stored column
    could hold either a DSL tree or that list, and every reader had to handle
    both. One shape in, one shape out.

    A single condition becomes a ``condition`` leaf; several become an ``and``
    group, which is what a flat conjunction means.

    Refuses a :class:`~fluxrules.domain.models.ConditionView` marked ``lossy``.
    Flattening ``OR(a, b)`` produces the same two leaves as ``AND(a, b)``, so
    rebuilding from it would quietly emit an ``and`` tree - a stricter rule
    that fires less often, with nothing raised and a row that looks perfectly
    healthy. The caller must pass the original ``condition_dsl`` instead.
    """
    if getattr(conditions, "lossy", False):
        raise LossyConditionRebuildError(
            "Refusing to rebuild a DSL tree from a lossy condition view: the "
            "original node was an OR/NOT (or nested under one) and rebuilding "
            "would silently turn it into an AND. Pass the rule's "
            "'condition_dsl' instead."
        )

    leaves = [
        {
            "type": "condition",
            "field": condition.fact,
            "op": condition.operator,
            "value": condition.value,
        }
        for condition in conditions
    ]

    if len(leaves) == 1:
        return leaves[0]
    return {"type": "and", "children": leaves}


def has_logic(condition_dsl: dict | list) -> bool:
    """Whether a DSL value carries at least one real condition.

    Used to refuse rules that cannot match anything. A composite node with no
    children is as empty as no node at all, and a nested tree of empty groups
    is still empty, so this recurses rather than just testing truthiness.

    Lives in the domain layer because both authoring (``Rule``) and
    persistence need the same answer, and they must not disagree about what
    counts as an empty rule.
    """
    if isinstance(condition_dsl, list):
        return any(has_logic(item) for item in condition_dsl if isinstance(item, dict))

    if not isinstance(condition_dsl, dict) or not condition_dsl:
        return False

    ctype = condition_dsl.get("type")

    if ctype in (None, "condition"):
        # A bare `{fact, operator, value}` dict (the legacy list element
        # shape) counts as logic; so does a `condition` node.
        return bool(condition_dsl.get("field") or condition_dsl.get("fact") or ctype == "condition")

    if ctype == "exists":
        return bool(condition_dsl.get("field") or condition_dsl.get("condition"))

    children = (
        condition_dsl.get("children")
        or condition_dsl.get("conditions")
        or condition_dsl.get("condition")
        or condition_dsl.get("child")
    )
    if isinstance(children, dict):
        children = [children]
    if not children:
        # Node types this function does not model (accumulate, sequence,
        # cross-fact joins) carry their logic in fields of their own. Treat
        # them as meaningful rather than rejecting a valid rule.
        return ctype not in ("and", "or", "group", "composite", "not")

    return any(has_logic(child) for child in children)


class UnsupportedDSLNodeError(ValueError):
    """A DSL node needs engine state this evaluator does not have."""


def evaluate_dsl(dsl: dict[str, Any], facts: dict[str, Any]) -> bool:
    """Evaluate a ``condition_dsl`` tree against a flat fact dict.

    Raises:
        UnsupportedDSLNodeError: For nodes requiring working memory.
    """
    if not isinstance(dsl, dict) or not dsl:
        return False

    ctype = dsl.get("type")

    if ctype == "condition":
        field = dsl.get("field", "")
        if field not in facts:
            return False
        return evaluate_operator(dsl.get("op", "=="), facts[field], dsl.get("value"))

    if ctype in ("and", "or", "group", "composite"):
        children = dsl.get("children") or dsl.get("conditions") or []
        if ctype == "and":
            logic = "AND"
        elif ctype == "or":
            logic = "OR"
        else:
            logic = str(dsl.get("logic") or dsl.get("op") or "AND").upper()
        if not children:
            # An empty group has no logic to match on. `all([])` would make it
            # match everything by vacuous truth - the failure this whole path
            # exists to avoid.
            return False
        results = [evaluate_dsl(child, facts) for child in children]
        return all(results) if logic == "AND" else any(results)

    if ctype == "not":
        inner = dsl.get("condition") or dsl.get("child")
        if inner:
            return not evaluate_dsl(inner, facts)
        inner_list = dsl.get("conditions") or dsl.get("children") or []
        if inner_list:
            return not any(evaluate_dsl(child, facts) for child in inner_list)
        return False

    if ctype == "exists":
        field = dsl.get("field")
        if field:
            return field in facts and facts[field] is not None
        inner = dsl.get("condition")
        return evaluate_dsl(inner, facts) if inner else False

    if ctype in _STATEFUL_NODES:
        raise UnsupportedDSLNodeError(
            f"DSL node type {ctype!r} requires working memory; evaluate this "
            "rule with PhreakEngine."
        )

    raise UnsupportedDSLNodeError(f"Unknown DSL node type {ctype!r}")
