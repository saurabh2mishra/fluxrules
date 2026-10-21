"""Dependency-free evaluation of a ``conditions`` tree.

``conditions`` is the canonical representation of rule logic. Anything that
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
    "UnsupportedConditionTreeNodeError",
    "conditions_to_tree",
    "evaluate_conditions",
    "has_logic",
]

_STATEFUL_NODES = frozenset({"accumulate", "sequence", "join", "cross_fact_join"})


def conditions_to_tree(conditions) -> dict:
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
    healthy. The caller must pass the original ``conditions`` instead.
    """
    if getattr(conditions, "lossy", False):
        raise LossyConditionRebuildError(
            "Refusing to rebuild a DSL tree from a lossy condition view: the "
            "original node was an OR/NOT (or nested under one) and rebuilding "
            "would silently turn it into an AND. Pass the rule's "
            "'conditions' instead."
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


def has_logic(conditions: dict | list) -> bool:
    """Whether a DSL value carries at least one real condition.

    Used to refuse rules that cannot match anything. A composite node with no
    children is as empty as no node at all, and a nested tree of empty groups
    is still empty, so this recurses rather than just testing truthiness.

    Lives in the domain layer because both authoring (``Rule``) and
    persistence need the same answer, and they must not disagree about what
    counts as an empty rule.
    """
    if isinstance(conditions, list):
        return any(has_logic(item) for item in conditions if isinstance(item, dict))

    if not isinstance(conditions, dict) or not conditions:
        return False

    ctype = conditions.get("type")

    if ctype in (None, "condition"):
        # A bare `{fact, operator, value}` dict (the legacy list element
        # shape) counts as logic; so does a `condition` node.
        return bool(conditions.get("field") or conditions.get("fact") or ctype == "condition")

    if ctype == "exists":
        return bool(conditions.get("field") or conditions.get("condition"))

    children = (
        conditions.get("children")
        or conditions.get("conditions")
        or conditions.get("condition")
        or conditions.get("child")
    )
    if isinstance(children, dict):
        children = [children]
    if not children:
        # Node types this function does not model (accumulate, sequence,
        # cross-fact joins) carry their logic in fields of their own. Treat
        # them as meaningful rather than rejecting a valid rule.
        return ctype not in ("and", "or", "group", "composite", "not")

    return any(has_logic(child) for child in children)


class UnsupportedConditionTreeNodeError(ValueError):
    """A DSL node needs engine state this evaluator does not have."""


def evaluate_conditions(dsl: dict[str, Any], facts: dict[str, Any]) -> bool:
    """Evaluate a ``conditions`` tree against a flat fact dict.

    Raises:
        UnsupportedConditionTreeNodeError: For nodes requiring working memory.
    """
    if not isinstance(dsl, dict) or not dsl:
        return False

    ctype = dsl.get("type")

    if ctype == "condition":
        field = dsl.get("field", "")
        if field not in facts:
            from fluxrules.domain.errors import FieldNotFoundError, is_field_typo

            if is_field_typo(field, facts):
                raise FieldNotFoundError.for_field(field, facts)
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
        results = [evaluate_conditions(child, facts) for child in children]
        return all(results) if logic == "AND" else any(results)

    if ctype == "not":
        inner = dsl.get("condition") or dsl.get("child")
        if inner:
            return not evaluate_conditions(inner, facts)
        inner_list = dsl.get("conditions") or dsl.get("children") or []
        if inner_list:
            return not any(evaluate_conditions(child, facts) for child in inner_list)
        return False

    if ctype == "exists":
        field = dsl.get("field")
        if field:
            return field in facts and facts[field] is not None
        inner = dsl.get("condition")
        return evaluate_conditions(inner, facts) if inner else False

    if ctype in _STATEFUL_NODES:
        raise UnsupportedConditionTreeNodeError(
            f"DSL node type {ctype!r} requires working memory; evaluate this "
            "rule with PhreakEngine."
        )

    raise UnsupportedConditionTreeNodeError(f"Unknown DSL node type {ctype!r}")
