from __future__ import annotations

from typing import Any, Dict, List

from app.compiler.rule_compiler import CompiledRule


class ExplanationEngine:
    def explain(self, rule: CompiledRule, fact: Dict[str, Any]) -> Dict[str, Any]:
        matched: List[str] = []
        for c in rule.constraints:
            if c.field in fact:
                matched.append(f"{c.field} {c.operator} {c.value} (fact={fact[c.field]!r})")
            else:
                matched.append(f"{c.field} {c.operator} {c.value} (fact=MISSING)")

        return {
            "rule": rule.id,
            "matched_conditions": matched,
            "facts": {k: fact[k] for k in sorted(fact.keys())},
        }
