from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class CompiledConstraint:
    field: str
    operator: str
    value: Any


@dataclass
class CompiledRule:
    id: str
    name: str = ""
    constraints: List[CompiledConstraint] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    priority: int = 0
    source_condition: Dict[str, Any] = field(default_factory=dict)
    group: str = "default"  # Add group attribute


class RuleCompiler:
    """
    Compiles existing FluxRules DSL dictionaries into canonical compiled rules.

    Backward compatible with nested group-based DSL already used by the runtime.
    """

    def compile_rule(self, rule_payload: Dict[str, Any]) -> CompiledRule:
        condition = rule_payload.get("condition_dsl") or {}
        constraints = self._extract_constraints(condition)
        actions = self._normalize_actions(rule_payload.get("action"))
        group = rule_payload.get("group") or "default"
        name = rule_payload.get("name") or str(rule_payload.get("id") or "unknown")
        return CompiledRule(
            id=str(rule_payload.get("id") or rule_payload.get("name") or "unknown"),
            name=name,
            constraints=constraints,
            actions=actions,
            priority=int(rule_payload.get("priority") or 0),
            source_condition=condition,
            group=group,
        )

    def compile_rules(self, rules: Sequence[Dict[str, Any]]) -> List[CompiledRule]:
        return [self.compile_rule(rule) for rule in rules]

    def _extract_constraints(self, condition: Dict[str, Any]) -> List[CompiledConstraint]:
        if not condition:
            return []

        condition_type = condition.get("type")
        if condition_type == "condition":
            field = condition.get("field")
            op = condition.get("op")
            if field is None or op is None:
                return []
            return [CompiledConstraint(field=str(field), operator=str(op), value=condition.get("value"))]

        if condition_type == "group":
            out: List[CompiledConstraint] = []
            for child in condition.get("children", []):
                out.extend(self._extract_constraints(child))
            return out

        return []

    def _normalize_actions(self, action: Any) -> List[str]:
        if action is None:
            return []
        if isinstance(action, str):
            return [action]
        if isinstance(action, Iterable):
            return [str(part) for part in action]
        return [str(action)]
