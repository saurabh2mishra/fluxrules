"""Single-fact boundary guardrail for rule condition DSLs (P0.3).

Why this exists
---------------
``PhreakEngine.evaluate(facts: dict)`` matches **one flattened fact** against each
rule independently. It is *not* a working-memory join engine: there is no
cross-fact join, no aggregation over a *collection* of facts, and no temporal /
sliding-window correlation. A rule that needs to correlate two events
("same card used in two countries within 5 minutes") cannot be expressed here and
must receive **pre-joined** facts from upstream (a stream processor / feature
store).

This module scans a rule's ``condition_dsl`` and reports constructs that imply
**cross-fact** semantics the engine cannot honor, so misuse fails fast (loudly)
instead of silently under-matching.

Design
------
- **Warn by default, raise on demand.** ``check_rules`` returns structured
  findings; ``enforce_single_fact_boundary`` logs warnings (default) or raises
  :class:`UnsupportedRuleShapeError` when ``strict=True``.
- **Sound and conservative.** We only flag shapes we can positively identify as
  cross-fact. The single-fact ``accumulate`` the engine actually supports (a
  single-field threshold) is reported as an *informational* note, not an error,
  because it works - it is just not a Drools-style collection aggregate.

Detection surface (P3 Track A)
------------------------------
Beyond explicit Drools/CEP **node types**, the guard also catches the shapes a
user is far more likely to actually write - each of which would otherwise load
clean and *silently under-match*:

- **Multiple bindings / entities** in one rule (``$o : Order`` × ``$c : Customer``).
- **Cross-entity dotted fields** (``order.*`` compared with ``customer.*``).
- **Field-to-field comparisons** (RHS names another field, not a literal).
- **Temporal / window keys** (``within``/``window_ms``/… on a normal node).

All detection is conservative: a single-entity, field-vs-literal rule - the
supported case - produces no finding.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FindingKind(str, Enum):
    """Severity/category of a boundary finding."""

    UNSUPPORTED = "unsupported"  # cross-fact shape the engine cannot honor
    SINGLE_FACT_NOTE = "single_fact_note"  # supported, but semantics worth noting


@dataclass(frozen=True)
class BoundaryFinding:
    """One boundary issue discovered in a rule's condition tree."""

    rule_id: Any
    kind: FindingKind
    node_type: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"[rule {self.rule_id}] {self.kind.value}: {self.message}"


class UnsupportedRuleShapeError(ValueError):
    """Raised (in strict mode) when a rule uses a cross-fact construct."""

    def __init__(self, findings: list[BoundaryFinding]) -> None:
        self.findings = findings
        joined = "; ".join(str(f) for f in findings)
        super().__init__(
            "Rule(s) use constructs unsupported by the single-fact engine: "
            f"{joined}. The engine matches one flattened fact per evaluation; "
            "correlate/aggregate upstream and pass pre-joined facts. See "
            "docs/engine-scope-and-limits.md."
        )


# Node types that, if they ever appear, denote multi-fact/temporal semantics.
# (Not currently produced by the builder, but guard against hand-authored or
# imported DSLs that borrow Drools/CEP vocabulary.) Widened in P3 Track A.4 to
# cover collection aggregates and Allen-style temporal operators.
_CROSS_FACT_NODE_TYPES = frozenset(
    {
        # joins / sources
        "join",
        "from",
        "collect",
        "correlate",
        # collection aggregates (vs. the single-field threshold ``accumulate``)
        "accumulate_collection",
        "aggregate",
        "group_by",
        # quantifiers over working memory
        "exists_collection",
        "not_exists_collection",
        "forall",
        "every",
        # temporal / CEP node types
        "temporal",
        "window",
        "sliding_window",
        "over",
        "sequence",
        "followed_by",
        "after",
        "before",
        "during",
        "overlaps",
        "meets",
        "starts",
        "finishes",
        "coincides",
    }
)

# Keys that, when present on *any* node, imply temporal / windowed correlation
# even if the node's ``type`` looks like an ordinary condition (P3 Track A.3).
_TEMPORAL_KEYS = frozenset(
    {
        "within",
        "window",
        "window_ms",
        "over_seconds",
        "sliding",
        "tumbling",
        "after_ms",
        "before_ms",
    }
)

# Keys that declare a *binding* (``$o : Order``) or an explicit fact type. Two or
# more distinct bindings/entities in one rule is the canonical join signature
# (P3 Track A.1).
_BINDING_KEYS = ("bind", "var", "binding", "alias")
_ENTITY_KEYS = ("fact_type", "entity", "type_of", "class")

# Keys whose value names *another field* (a field-to-field comparison). The
# engine only ever compares a field to a literal ``value``; a field-to-field
# compare is a join it cannot perform (P3 Track A.2).
_RHS_FIELD_REF_KEYS = (
    "field2",
    "rhs_field",
    "value_field",
    "other_field",
    "right_field",
)
# Keys whose value may hold a *structured* field reference (``{"field": "x"}``).
_RHS_STRUCTURED_KEYS = ("value", "rhs", "right")
_STRUCTURED_REF_KEYS = ("field", "$field", "$ref", "ref")


def _dotted_prefix(name: Any) -> str | None:
    """Return the entity prefix of a dotted field name (``order.x`` -> ``order``)."""
    if isinstance(name, str) and "." in name:
        return name.split(".", 1)[0]
    return None


def _rhs_field_ref(node: dict[str, Any]) -> str | None:
    """Return the RHS field name if this condition compares field-to-field.

    Detects both an explicit field-reference key (``field2``/``rhs_field``/…) and
    a structured reference nested in ``value``/``rhs``/``right``
    (``{"field": "other"}``). A plain literal ``value`` (string, number, …) is
    *not* a field reference and yields ``None`` - the single-fact engine compares
    the field to that literal, which it fully supports.
    """
    for key in _RHS_FIELD_REF_KEYS:
        candidate = node.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    for key in _RHS_STRUCTURED_KEYS:
        candidate = node.get(key)
        if isinstance(candidate, dict):
            for ref_key in _STRUCTURED_REF_KEYS:
                ref = candidate.get(ref_key)
                if isinstance(ref, str) and ref:
                    return ref
    return None


def _walk(node: Any) -> Iterable[dict[str, Any]]:
    """Yield every dict node in a condition tree (depth-first)."""
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("conditions") or node.get("children") or []:
        yield from _walk(child)
    inner = node.get("condition")
    if isinstance(inner, dict):
        yield from _walk(inner)


def check_condition(rule_id: Any, condition: Any) -> list[BoundaryFinding]:
    """Return boundary findings for a single rule's ``condition_dsl``.

    Detects, conservatively, every shape that implies the engine would have to
    correlate more than the one flattened fact it is given:

    - **Node type** (``join``/``window``/``aggregate``/… - Drools/CEP vocabulary).
    - **Temporal keys** (``within``/``window_ms``/… on an otherwise normal node).
    - **Field-to-field comparison** (RHS names another field, not a literal).
    - **Multiple bindings / entities** (``$o : Order`` × ``$c : Customer``).
    - **Cross-entity dotted prefixes** (``order.*`` compared with ``customer.*``).

    Single-entity, field-vs-literal rules - the supported case - yield no finding.
    """
    findings: list[BoundaryFinding] = []
    bindings: set[str] = set()
    entities: set[str] = set()
    dotted_prefixes: set[str] = set()

    for node in _walk(condition):
        ctype = str(node.get("type", ""))

        # A.1 (collect): bindings / explicit entity annotations on this node.
        for key in _BINDING_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val:
                bindings.add(val)
        for key in _ENTITY_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val:
                entities.add(val)

        # A.2 (collect): dotted entity prefix on this node's field.
        prefix = _dotted_prefix(node.get("field"))
        if prefix is not None:
            dotted_prefixes.add(prefix)

        if ctype in _CROSS_FACT_NODE_TYPES:
            findings.append(
                BoundaryFinding(
                    rule_id=rule_id,
                    kind=FindingKind.UNSUPPORTED,
                    node_type=ctype,
                    message=(
                        f"node type '{ctype}' implies cross-fact/temporal "
                        "correlation, which the single-fact engine cannot evaluate"
                    ),
                )
            )
            continue

        # A.3: temporal / windowing keys on an otherwise ordinary node.
        temporal_hit = next((k for k in _TEMPORAL_KEYS if k in node), None)
        if temporal_hit is not None:
            findings.append(
                BoundaryFinding(
                    rule_id=rule_id,
                    kind=FindingKind.UNSUPPORTED,
                    node_type="temporal_key",
                    message=(
                        f"key '{temporal_hit}' implies a temporal/sliding window; "
                        "the single-fact engine has no event clock or window state"
                    ),
                )
            )

        # A.2: field-to-field comparison (RHS is a field ref, not a literal).
        rhs_field = _rhs_field_ref(node)
        if rhs_field is not None:
            lhs_field = node.get("field")
            findings.append(
                BoundaryFinding(
                    rule_id=rule_id,
                    kind=FindingKind.UNSUPPORTED,
                    node_type="cross_field_ref",
                    message=(
                        f"comparison of field '{lhs_field}' to another field "
                        f"'{rhs_field}' is a join; the engine compares a field to "
                        "a literal only"
                    ),
                )
            )

        if ctype == "accumulate":
            # The engine supports a *single-field threshold* accumulate only.
            # If the node references a collection/source it is being used as a
            # Drools-style aggregate, which is unsupported.
            if any(k in node for k in ("source", "from", "over", "group_by")):
                findings.append(
                    BoundaryFinding(
                        rule_id=rule_id,
                        kind=FindingKind.UNSUPPORTED,
                        node_type=ctype,
                        message=(
                            "'accumulate' over a collection/source is not "
                            "supported; only single-field threshold accumulate "
                            "is honored (agg compared to 'threshold')"
                        ),
                    )
                )
            else:
                findings.append(
                    BoundaryFinding(
                        rule_id=rule_id,
                        kind=FindingKind.SINGLE_FACT_NOTE,
                        node_type=ctype,
                        message=(
                            "'accumulate' is evaluated as a single-fact field "
                            "threshold (not a collection aggregate)"
                        ),
                    )
                )

    # A.1: two or more distinct bindings / entities in one rule = a join.
    distinct = bindings | entities
    if len(distinct) >= 2:
        findings.append(
            BoundaryFinding(
                rule_id=rule_id,
                kind=FindingKind.UNSUPPORTED,
                node_type="multi_binding",
                message=(
                    "rule binds multiple facts/entities "
                    f"({', '.join(sorted(distinct))}); the single-fact engine "
                    "matches one fact and cannot join across bindings"
                ),
            )
        )

    # A.2: fields from two or more distinct entities (``order.*`` × ``customer.*``)
    # is a join expressed through field naming. A single consistent prefix is fine.
    if len(dotted_prefixes) >= 2:
        findings.append(
            BoundaryFinding(
                rule_id=rule_id,
                kind=FindingKind.UNSUPPORTED,
                node_type="cross_entity_fields",
                message=(
                    "fields reference multiple entities "
                    f"({', '.join(sorted(dotted_prefixes))}.*); correlating "
                    "across entities is a join the single-fact engine cannot do"
                ),
            )
        )

    return findings


def check_rules(rules: Iterable[Any]) -> list[BoundaryFinding]:
    """Scan an iterable of Rule objects / dicts for boundary findings."""
    findings: list[BoundaryFinding] = []
    for rule in rules:
        if isinstance(rule, dict):
            rid = rule.get("id")
            condition = rule.get("condition_dsl")
        else:
            rid = getattr(rule, "id", None)
            condition = getattr(rule, "condition_dsl", None)
        if condition is not None:
            findings.extend(check_condition(rid, condition))
    return findings


def enforce_single_fact_boundary(
    rules: Iterable[Any], *, strict: bool = False
) -> list[BoundaryFinding]:
    """Warn (default) or raise (strict) on cross-fact rule shapes.

    Args:
        rules: Rule objects or dicts to scan.
        strict: when True, raise :class:`UnsupportedRuleShapeError` if any
            ``UNSUPPORTED`` finding is present. When False (default), log a
            warning per unsupported finding and return the findings.

    Returns:
        All findings (including informational single-fact notes).
    """
    findings = check_rules(rules)
    unsupported = [f for f in findings if f.kind is FindingKind.UNSUPPORTED]

    if unsupported and strict:
        raise UnsupportedRuleShapeError(unsupported)

    for f in unsupported:
        logger.warning(
            "single-fact boundary: %s (this rule will not behave as a cross-fact "
            "rule; pre-join upstream - see docs/engine-scope-and-limits.md)",
            f,
        )
    return findings


__all__ = [
    "BoundaryFinding",
    "FindingKind",
    "UnsupportedRuleShapeError",
    "check_condition",
    "check_rules",
    "enforce_single_fact_boundary",
]
