from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate
from typing import List, Dict, Any, Optional
import json

class ConflictDetector:
    def __init__(self, db: Session):
        self.db = db
    
    def detect_all_conflicts(self) -> Dict[str, Any]:
        rules = self.db.query(Rule).filter(Rule.enabled == True).all()
        
        conflicts = []
        conflicts.extend(self._detect_duplicate_conditions(rules))
        conflicts.extend(self._detect_priority_collisions(rules))
        
        return {"conflicts": conflicts}
    
    def check_new_rule_conflicts(self, new_rule: RuleCreate) -> List[Dict[str, Any]]:
        """Check if a new rule would conflict with existing rules"""
        try:
            existing_rules = self.db.query(Rule).filter(Rule.enabled == True).all()
        except Exception as e:
            print(f"Error querying rules: {e}")
            return []
        
        conflicts = []
        
        # Check for duplicate conditions
        try:
            new_condition = json.dumps(new_rule.condition_dsl, sort_keys=True)
            for rule in existing_rules:
                try:
                    # existing_condition = json.dumps(json.loads(rule.condition_dsl), sort_keys=True)
                    existing_condition = json.dumps(rule.condition_dsl, sort_keys=True) 
                    if new_condition == existing_condition:
                        conflicts.append({
                            "type": "duplicate_condition",
                            "existing_rule_id": rule.id,
                            "existing_rule_name": rule.name,
                            "description": f"Identical condition exists in rule '{rule.name}' (ID: {rule.id})"
                        })
                except Exception as e:
                    print(f"Error comparing conditions for rule {rule.id}: {e}")
                    continue
        except Exception as e:
            print(f"Error checking duplicate conditions: {e}")
        
        # Check for priority collisions
        try:
            for rule in existing_rules:
                rule_group = rule.group or "default"
                new_group = new_rule.group or "default"
                
                if rule_group == new_group and rule.priority == new_rule.priority:
                    conflicts.append({
                        "type": "priority_collision",
                        "existing_rule_id": rule.id,
                        "existing_rule_name": rule.name,
                        "group": new_group,
                        "priority": new_rule.priority,
                        "description": f"Rule '{rule.name}' (ID: {rule.id}) has same priority {new_rule.priority} in group '{new_group}'"
                    })
        except Exception as e:
            print(f"Error checking priority collisions: {e}")
        
        return conflicts
    
    def check_update_rule_conflicts(self, rule_id: int, updated_rule: RuleUpdate) -> List[Dict[str, Any]]:
        """Check if updating a rule would cause conflicts"""
        try:
            existing_rules = self.db.query(Rule).filter(
                Rule.enabled == True,
                Rule.id != rule_id
            ).all()
            
            current_rule = self.db.query(Rule).filter(Rule.id == rule_id).first()
            if not current_rule:
                return []
        except Exception as e:
            print(f"Error querying rules for update check: {e}")
            return []
        
        conflicts = []
        
        # Get updated values or use current ones
        try:
            # new_condition_dsl = updated_rule.condition_dsl if updated_rule.condition_dsl else json.loads(current_rule.condition_dsl)
            new_condition_dsl = updated_rule.condition_dsl if updated_rule.condition_dsl else current_rule.condition_dsl
            new_priority = updated_rule.priority if updated_rule.priority is not None else current_rule.priority
            new_group = updated_rule.group if updated_rule.group is not None else current_rule.group
        except Exception as e:
            print(f"Error parsing rule data: {e}")
            return []
        
        # Check for duplicate conditions
        if updated_rule.condition_dsl:
            try:
                new_condition = json.dumps(new_condition_dsl, sort_keys=True)
                for rule in existing_rules:
                    try:
                        # existing_condition = json.dumps(json.loads(rule.condition_dsl), sort_keys=True)
                        existing_condition = json.dumps(rule.condition_dsl, sort_keys=True)
                        if new_condition == existing_condition:
                            conflicts.append({
                                "type": "duplicate_condition",
                                "existing_rule_id": rule.id,
                                "existing_rule_name": rule.name,
                                "description": f"Identical condition exists in rule '{rule.name}' (ID: {rule.id})"
                            })
                    except Exception as e:
                        print(f"Error comparing conditions: {e}")
                        continue
            except Exception as e:
                print(f"Error in duplicate condition check: {e}")
        
        # Check for priority collisions
        if updated_rule.priority is not None or updated_rule.group is not None:
            try:
                for rule in existing_rules:
                    rule_group = rule.group or "default"
                    check_group = new_group or "default"
                    
                    if rule_group == check_group and rule.priority == new_priority:
                        conflicts.append({
                            "type": "priority_collision",
                            "existing_rule_id": rule.id,
                            "existing_rule_name": rule.name,
                            "group": check_group,
                            "priority": new_priority,
                            "description": f"Rule '{rule.name}' (ID: {rule.id}) has same priority {new_priority} in group '{check_group}'"
                        })
            except Exception as e:
                print(f"Error in priority collision check: {e}")
        
        return conflicts
    
    def _detect_duplicate_conditions(self, rules: List[Rule]) -> List[Dict[str, Any]]:
        conflicts = []
        condition_map = {}
        
        for rule in rules:
            try:
                # condition_dict = json.loads(rule.condition_dsl)
                condition_dict = rule.condition_dsl
                condition_str = json.dumps(condition_dict, sort_keys=True)
                
                if condition_str in condition_map:
                    conflicts.append({
                        "type": "duplicate_condition",
                        "rule1_id": condition_map[condition_str]['id'],
                        "rule1_name": condition_map[condition_str]['name'],
                        "rule2_id": rule.id,
                        "rule2_name": rule.name,
                        "description": f"Rules '{condition_map[condition_str]['name']}' (ID: {condition_map[condition_str]['id']}) and '{rule.name}' (ID: {rule.id}) have identical conditions"
                    })
                else:
                    condition_map[condition_str] = {'id': rule.id, 'name': rule.name}
            except Exception as e:
                print(f"Error processing rule {rule.id}: {e}")
                continue
        
        return conflicts
    
    def _detect_priority_collisions(self, rules: List[Rule]) -> List[Dict[str, Any]]:
        conflicts = []
        priority_map = {}
        
        for rule in rules:
            try:
                key = (rule.group or "default", rule.priority)
                if key in priority_map:
                    priority_map[key].append({'id': rule.id, 'name': rule.name})
                else:
                    priority_map[key] = [{'id': rule.id, 'name': rule.name}]
            except Exception as e:
                print(f"Error processing rule priority {rule.id}: {e}")
                continue
        
        for (group, priority), rule_list in priority_map.items():
            if len(rule_list) > 1:
                rule_names = ", ".join([f"'{r['name']}' (ID: {r['id']})" for r in rule_list])
                conflicts.append({
                    "type": "priority_collision",
                    "group": group,
                    "priority": priority,
                    "rules": rule_list,
                    "description": f"Multiple rules in group '{group}' have priority {priority}: {rule_names}"
                })
        
        return conflicts