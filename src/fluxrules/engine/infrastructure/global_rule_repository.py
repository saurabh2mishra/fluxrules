"""Global rule repository for unified rule space."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from fluxrules.domain.unified_rule import Rule

logger = logging.getLogger(__name__)

# Fields the runtime consumes. Anything outside this set is not part of the
# engine's contract with a rule object.
_RUNTIME_FIELDS = (
    "id",
    "name",
    "condition_dsl",
    "action",
    "actions",
    "priority",
    "enabled",
    "domain",
    "tags",
    "sla_latency_ms",
    "version",
    "metadata",
)


def _coerce_condition_dsl(value: Any) -> Any:
    """Turn the persistence layer's condition shapes into a real DSL dict.

    ``domain_rule_to_orm`` stores an :class:`EngineRule`'s conditions as a bare
    list of ``{fact, operator, value}`` dicts, and some callers hand back the
    raw JSON string straight from the column. Neither shape is a DSL tree, and
    the engines only ever traverse DSL trees - so a rule in either shape was
    loaded without error and then silently never matched anything.

    Converting here fixes the rules rather than merely tolerating them. Values
    that are already DSL dicts are returned untouched, so authored rules are
    unaffected.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return value

    if not isinstance(value, list):
        return value

    # A list of persisted conditions is an implicit AND over leaf comparisons.
    leaves = []
    for condition in value:
        if not isinstance(condition, dict):
            return value
        field = condition.get("fact", condition.get("field", condition.get("attribute")))
        op = condition.get("operator", condition.get("op"))
        if not field or not op:
            return value
        leaves.append(
            {
                "type": "condition",
                "field": field,
                "op": op,
                "value": condition.get("value"),
            }
        )

    if not leaves:
        return value
    if len(leaves) == 1:
        return leaves[0]
    return {"type": "and", "children": leaves}


def normalize_rule(rule: Any) -> Rule:
    """Coerce anything rule-shaped into the canonical :class:`fluxrules.Rule`.

    The repository used to store whatever it was handed, so two different
    classes could sit in the same repository and engines had to duck-type
    across them. Normalising here means there is exactly one type inside the
    engine, without any engine internals needing to change.

    Construction always passes ``persist=False``, so loading rules into an
    engine can never trigger a database write - the hazard that made a blind
    migration off the old non-persisting type dangerous.

    Note on cost: ``model_construct`` looks like the cheap option here but
    measured ~14x *slower* than normal validated construction (14.0 us vs
    1.0 us), because it has to reconstruct defaults for unset fields. The
    validated path is both faster and stricter, so it is preferred.

    Persistence shapes are *converted* rather than tolerated: see
    :func:`_coerce_condition_dsl`. A rule whose ``condition_dsl`` was a bare
    list used to be stored unvalidated and then never matched anything, so
    "preserving" it preserved a silent failure.

    The unvalidated fallback remains for genuinely foreign shapes - notably
    rules carrying a non-integer ``id``, which engines have always accepted
    because they only use the id as an opaque key.
    """
    from fluxrules.domain.unified_rule import Rule as CanonicalRule

    if isinstance(rule, CanonicalRule):
        return rule

    if isinstance(rule, dict):
        data = {k: rule.get(k) for k in _RUNTIME_FIELDS if k in rule}
    else:
        data = {k: getattr(rule, k) for k in _RUNTIME_FIELDS if hasattr(rule, k)}

    # ``EngineRule`` (the persistence/domain type) exposes its logic as the
    # authoritative ``condition_dsl`` tree. Without this the whole condition
    # tree was dropped and the rule silently matched nothing once inside an
    # engine.
    if not data.get("condition_dsl") and getattr(rule, "condition_dsl", None):
        data["condition_dsl"] = rule.condition_dsl

    actions = data.get("actions") or ()
    action = data.get("action") or ""
    if isinstance(actions, str):
        actions = tuple(a.strip() for a in actions.split("\n") if a.strip())
    else:
        actions = tuple(actions)
    if actions and not action:
        action = actions[0]
    elif action and not actions:
        actions = (action,)

    fields = {
        "id": data.get("id", 0),
        "name": data.get("name", "") or "",
        "condition_dsl": _coerce_condition_dsl(data.get("condition_dsl") or {}),
        "action": action,
        "actions": actions,
        "priority": data.get("priority", 0) or 0,
        "enabled": data.get("enabled", True),
        "domain": data.get("domain", "default") or "default",
        "tags": frozenset(data.get("tags") or ()),
        "sla_latency_ms": data.get("sla_latency_ms", 100) or 100,
        "version": data.get("version", "1.0") or "1.0",
        "metadata": data.get("metadata") or {},
        "description": data.get("description", "") or "",
        "persist": False,
    }

    try:
        return CanonicalRule(**fields)
    except ValidationError:
        # Remaining shapes are ones the engine genuinely evaluates but Pydantic
        # rejects - overwhelmingly a non-integer ``id``, which works end to end
        # because engines only ever use the id as an opaque key. Rejecting them
        # here would break working rules, so they are stored unvalidated.
        logger.debug(
            "Rule %s did not pass validation during normalisation; storing "
            "unvalidated to preserve prior engine behaviour.",
            fields["id"],
        )
        return CanonicalRule.model_construct(created_at=None, updated_at=None, **fields)


class GlobalRuleRepository:
    """All rules in a single space, indexed for fast lookup.

    Supports up to ``max_rules`` rules. Provides O(1) lookup by ID,
    O(n) scan by domain/tags (with indexed shortcuts).

    Every rule is normalised to the canonical :class:`fluxrules.Rule` on the
    way in, so the repository holds exactly one type.
    """

    def __init__(self, max_rules: int = 50_000) -> None:
        self.max_rules = max_rules
        self._rules: dict[int, Rule] = {}
        self._by_domain: dict[str, set[int]] = {}
        self._by_tag: dict[str, set[int]] = {}

    @property
    def rules(self) -> dict[int, Rule]:
        return self._rules

    def add_rule(self, rule: Any) -> None:
        """Add a single rule, normalising it to the canonical ``Rule``.

        Accepts a ``Rule``, a dict, or any object exposing the runtime fields.
        """
        rule = normalize_rule(rule)

        if len(self._rules) >= self.max_rules:
            raise ValueError(
                f"Repository full ({self.max_rules} rules). "
                "Increase max_rules or remove unused rules."
            )
        self._rules[rule.id] = rule
        self._by_domain.setdefault(rule.domain, set()).add(rule.id)
        for tag in rule.tags:
            self._by_tag.setdefault(tag, set()).add(rule.id)

    def add_rules(self, rules: list[Any]) -> None:
        """Add multiple rules (accepts ``Rule`` objects and dicts)."""
        for rule in rules:
            self.add_rule(rule)

    def get(self, rule_id: int) -> Rule | None:
        """Get rule by ID (O(1))."""
        return self._rules.get(rule_id)

    def get_by_domain(self, domain: str) -> list[Rule]:
        """Get all rules in a domain."""
        ids = self._by_domain.get(domain, set())
        return [self._rules[rid] for rid in ids if rid in self._rules]

    def get_by_tag(self, tag: str) -> list[Rule]:
        """Get all rules with a tag."""
        ids = self._by_tag.get(tag, set())
        return [self._rules[rid] for rid in ids if rid in self._rules]

    def get_all_domains(self) -> list[str]:
        """Get list of all domains."""
        return list(self._by_domain.keys())

    def remove(self, rule_id: int) -> None:
        """Remove a rule."""
        rule = self._rules.pop(rule_id, None)
        if rule:
            domain_set = self._by_domain.get(rule.domain)
            if domain_set:
                domain_set.discard(rule_id)
            for tag in rule.tags:
                tag_set = self._by_tag.get(tag)
                if tag_set:
                    tag_set.discard(rule_id)

    def clear(self) -> None:
        """Remove all rules."""
        self._rules.clear()
        self._by_domain.clear()
        self._by_tag.clear()

    def __len__(self) -> int:
        return len(self._rules)


class _DeprecatedRuntimeRule:
    """Deprecated shim: ``RuntimeRule`` -> :class:`fluxrules.Rule`.

    ``RuntimeRule`` was a third rule representation that production code never
    constructed. It is gone; the repository now normalises everything to the
    canonical :class:`fluxrules.Rule`.

    Kept callable for one release so existing call sites keep working. It is
    not a class you can subclass or use with ``isinstance`` - it builds a
    ``Rule`` and returns it.

    ``persist=False`` is forced. ``RuntimeRule`` never touched a database, and
    ``Rule`` persists by default, so omitting this would turn every migrated
    call site - including benchmark setup - into a series of database writes.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> Rule:  # type: ignore[misc]  # intentional factory: builds and returns a canonical Rule, not an instance of this shim
        _warn_runtime_rule()
        from fluxrules.domain.unified_rule import Rule as CanonicalRule

        if args:
            names = (
                "id",
                "name",
                "condition_dsl",
                "action",
                "priority",
                "enabled",
                "domain",
                "tags",
                "sla_latency_ms",
                "version",
                "metadata",
            )
            kwargs.update(dict(zip(names, args)))
        kwargs.setdefault("persist", False)
        return CanonicalRule(**kwargs)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Rule:
        """Deprecated. Use ``Rule(**data)`` or let the repository normalise."""
        _warn_runtime_rule()
        return normalize_rule(data)


def _warn_runtime_rule() -> None:
    import warnings

    warnings.warn(
        "RuntimeRule is deprecated and will be removed in the next release; "
        "use the canonical 'from fluxrules import Rule' instead. Pass "
        "persist=False to keep the old non-persisting behaviour.",
        DeprecationWarning,
        stacklevel=3,
    )


def __getattr__(name: str) -> Any:
    """Deprecated aliases ``Rule`` and ``RuntimeRule``.

    Implemented as a module ``__getattr__`` (PEP 562) so the warning fires on
    *access* rather than on import of this module, which would make it
    unavoidable noise for internal callers that never touch the old names.
    """
    if name == "RuntimeRule":
        return _DeprecatedRuntimeRule
    if name == "Rule":
        import warnings

        warnings.warn(
            "fluxrules.engine.infrastructure.Rule is deprecated; use the "
            "canonical 'from fluxrules import Rule'. Three classes named "
            "'Rule' were importable from three modules, which caused real "
            "import mistakes.",
            DeprecationWarning,
            stacklevel=2,
        )
        from fluxrules.domain.unified_rule import Rule as CanonicalRule

        return CanonicalRule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
