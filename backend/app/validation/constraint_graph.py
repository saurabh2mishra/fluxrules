from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set

from app.compiler.rule_compiler import CompiledRule


@dataclass
class ConstraintGraph:
    rule_to_fields: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    field_to_rules: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))


class ConstraintGraphBuilder:
    def build(self, compiled_rules: List[CompiledRule]) -> ConstraintGraph:
        graph = ConstraintGraph()
        for rule in compiled_rules:
            for constraint in rule.constraints:
                graph.rule_to_fields[rule.id].add(constraint.field)
                graph.field_to_rules[constraint.field].add(rule.id)
        return graph
