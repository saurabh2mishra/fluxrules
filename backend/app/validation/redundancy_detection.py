from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.compiler.rule_compiler import CompiledRule
from app.validation._normalization import intervals_by_field


@dataclass
class RedundantRule:
    redundant_rule_id: str
    subsuming_rule_id: str


class RedundancyDetector:
    def detect(self, compiled_rules: List[CompiledRule]) -> List[RedundantRule]:
        out: List[RedundantRule] = []
        by_id = {rule.id: intervals_by_field(rule) for rule in compiled_rules}
        for candidate in compiled_rules:
            c_ranges = by_id[candidate.id]
            for parent in compiled_rules:
                if candidate.id == parent.id:
                    continue
                p_ranges = by_id[parent.id]
                if self._subsumes(p_ranges, c_ranges):
                    out.append(RedundantRule(redundant_rule_id=candidate.id, subsuming_rule_id=parent.id))
                    break
        return out

    def _subsumes(self, maybe_parent: dict, maybe_child: dict) -> bool:
        if not maybe_child:
            return False
        for field, child_intervals in maybe_child.items():
            parent_intervals = maybe_parent.get(field)
            if not parent_intervals:
                return False
            for c in child_intervals:
                if not any(p.contains(c) for p in parent_intervals):
                    return False
        return True
