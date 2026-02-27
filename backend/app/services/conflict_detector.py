from sqlalchemy.orm import Session
from app.engine.optimized_rete_engine import OptimizedReteEngine
from app.schemas.rule import RuleCreate, RuleUpdate
from typing import List, Dict, Any
import json

class ConflictDetector:
    def __init__(self, db: Session):
        self.db = db
        self.engine = OptimizedReteEngine(db)
        self.rules = self.engine.cache.get_rules(db)
        self.group_priority_map = self._build_priority_map(self.rules)

    def _build_priority_map(self, rules):
        priority_map = {}
        for rule in rules:
            key = (rule["group"] or "default", rule["priority"])
            if key not in priority_map:
                priority_map[key] = []
            priority_map[key].append(rule)
        return priority_map

    def check_new_rule_conflicts(self, new_rule: RuleCreate) -> List[Dict[str, Any]]:
        conflicts = []
        # Use RETE to find candidate rules that would match the new rule's condition
        event = new_rule.condition_dsl if isinstance(new_rule.condition_dsl, dict) else json.loads(new_rule.condition_dsl)
        # Simulate as event, get matching rules
        result = self.engine.evaluate(event, use_rete=True)
        matched_rules = result.get("matched_rules", [])
        new_condition = json.dumps(event, sort_keys=True)
        for rule in matched_rules:
            # Check for duplicate condition
            existing_rule = next((r for r in self.rules if r["id"] == rule["id"]), None)
            if existing_rule:
                existing_condition = json.dumps(existing_rule["condition_dsl"], sort_keys=True)
                if new_condition == existing_condition:
                    conflicts.append({
                        "type": "duplicate_condition",
                        "existing_rule_id": rule["id"],
                        "existing_rule_name": rule["name"],
                        "description": f"Identical condition exists in rule '{rule['name']}' (ID: {rule['id']})"
                    })
        # Priority collision (fast map)
        new_group = new_rule.group or "default"
        new_priority = new_rule.priority
        for rule in self.group_priority_map.get((new_group, new_priority), []):
            conflicts.append({
                "type": "priority_collision",
                "existing_rule_id": rule["id"],
                "existing_rule_name": rule["name"],
                "group": new_group,
                "priority": new_priority,
                "description": f"Rule '{rule['name']}' (ID: {rule['id']}) has same priority {new_priority} in group '{new_group}'"
            })
        return conflicts

    def check_update_rule_conflicts(self, rule_id: int, updated_rule: RuleUpdate) -> List[Dict[str, Any]]:
        conflicts = []
        current_rule = next((r for r in self.rules if r["id"] == rule_id), None)
        if not current_rule:
            return []
        new_condition_dsl = updated_rule.condition_dsl if updated_rule.condition_dsl else current_rule["condition_dsl"]
        new_priority = updated_rule.priority if updated_rule.priority is not None else current_rule["priority"]
        new_group = updated_rule.group if updated_rule.group is not None else current_rule["group"]
        event = new_condition_dsl
        result = self.engine.evaluate(event, use_rete=True)
        matched_rules = result.get("matched_rules", [])
        new_condition = json.dumps(event, sort_keys=True)
        for rule in matched_rules:
            if rule["id"] == rule_id:
                continue
            existing_rule = next((r for r in self.rules if r["id"] == rule["id"]), None)
            if existing_rule:
                existing_condition = json.dumps(existing_rule["condition_dsl"], sort_keys=True)
                if new_condition == existing_condition:
                    conflicts.append({
                        "type": "duplicate_condition",
                        "existing_rule_id": rule["id"],
                        "existing_rule_name": rule["name"],
                        "description": f"Identical condition exists in rule '{rule['name']}' (ID: {rule['id']})"
                    })
        for rule in self.group_priority_map.get((new_group, new_priority), []):
            if rule["id"] == rule_id:
                continue
            conflicts.append({
                "type": "priority_collision",
                "existing_rule_id": rule["id"],
                "existing_rule_name": rule["name"],
                "group": new_group,
                "priority": new_priority,
                "description": f"Rule '{rule['name']}' (ID: {rule['id']}) has same priority {new_priority} in group '{new_group}'"
            })
        return conflicts

    def detect_all_conflicts(self) -> Dict[str, Any]:
        conflicts = []
        # Duplicate conditions
        condition_map = {}
        for rule in self.rules:
            condition_str = json.dumps(rule["condition_dsl"], sort_keys=True)
            if condition_str in condition_map:
                conflicts.append({
                    "type": "duplicate_condition",
                    "rule1_id": condition_map[condition_str]["id"],
                    "rule1_name": condition_map[condition_str]["name"],
                    "rule2_id": rule["id"],
                    "rule2_name": rule["name"],
                    "description": f"Rules '{condition_map[condition_str]['name']}' (ID: {condition_map[condition_str]['id']}) and '{rule['name']}' (ID: {rule['id']}) have identical conditions"
                })
            else:
                condition_map[condition_str] = rule
        # Priority collisions
        for (group, priority), rule_list in self.group_priority_map.items():
            if len(rule_list) > 1:
                rule_names = ", ".join([f"'{r['name']}' (ID: {r['id']})" for r in rule_list])
                conflicts.append({
                    "type": "priority_collision",
                    "group": group,
                    "priority": priority,
                    "rules": rule_list,
                    "description": f"Multiple rules in group '{group}' have priority {priority}: {rule_names}"
                })
        return {"conflicts": conflicts}
