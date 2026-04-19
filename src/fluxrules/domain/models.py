from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


Fact = dict[str, Any]


@dataclass(slots=True, frozen=True)
class RuleCondition:
    fact: str
    operator: str
    value: Any


@dataclass(slots=True, frozen=True)
class Rule:
    id: str
    conditions: tuple[RuleCondition, ...]
    actions: tuple[str, ...] = ()
    priority: int = 0


@dataclass(slots=True, frozen=True)
class Ruleset:
    id: str
    rules: tuple[Rule, ...] = ()


@dataclass(slots=True)
class EvaluationResult:
    ruleset_id: str
    matched_rule_ids: list[str]
    actions: list[str]
    trace: list[dict[str, Any]] = field(default_factory=list)
    execution_id: str = field(default_factory=lambda: str(uuid4()))
