from typing import List
from app.compiler.rule_compiler import CompiledRule

class PriorityCollisionDetector:
    """Detects rules with same group and priority."""
    def detect(self, compiled_rules: List[CompiledRule]) -> List[dict]:
        group_priority_map = {}
        collisions = []
        for rule in compiled_rules:
            key = (rule.group, rule.priority)
            group_priority_map.setdefault(key, []).append(rule)
        for (group, priority), rules in group_priority_map.items():
            if len(rules) > 1:
                rule_names = ", ".join([f"'{r.name}' (ID: {r.id})" for r in rules])
                collisions.append({
                    "group": group,
                    "priority": priority,
                    "rules": [r.id for r in rules],
                    "description": f"Priority collision in group '{group}' with priority {priority}: {rule_names}"
                })
        return collisions
