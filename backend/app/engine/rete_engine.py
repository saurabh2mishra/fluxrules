from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.engine.dsl_parser import DSLParser
from app.engine.profiler import RuleProfiler
from typing import Dict, Any, List, Optional
import json

class ReteEngine:
    def __init__(self, db: Session):
        self.db = db
        self.parser = DSLParser()
        self.profiler = RuleProfiler()
        self.rulesets = {}
        self._load_rules()
    
    def _load_rules(self):
        rules = self.db.query(Rule).filter(Rule.enabled == True).order_by(Rule.priority.desc()).all()
        
        for rule in rules:
            self._register_rule(rule)
    
    def _register_rule(self, rule: Rule):
        pass
    
    def reload_rules(self):
        self.rulesets = {}
        self._load_rules()
    
    def simulate(self, event: Dict[str, Any], rule_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        rules = self.db.query(Rule).filter(Rule.enabled == True)
        if rule_ids:
            rules = rules.filter(Rule.id.in_(rule_ids))
        rules = rules.order_by(Rule.priority.desc()).all()
        
        matched_rules = []
        execution_order = []
        explanations = {}
        
        for rule in rules:
            # condition_dsl = json.loads(rule.condition_dsl)
            condition_dsl = rule.condition_dsl
            if self._evaluate_condition(condition_dsl, event):
                matched_rules.append({
                    "id": rule.id,
                    "name": rule.name,
                    "priority": rule.priority,
                    "action": rule.action
                })
                execution_order.append(rule.id)
                explanations[rule.id] = self._generate_explanation(rule, event)
        
        return {
            "matched_rules": matched_rules,
            "execution_order": execution_order,
            "explanations": explanations,
            "dry_run": True
        }
    
    def _evaluate_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> bool:
        if condition["type"] == "condition":
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            
            event_value = event.get(field)
            if event_value is None:
                return False
            
            if op == ">":
                return event_value > value
            elif op == ">=":
                return event_value >= value
            elif op == "<":
                return event_value < value
            elif op == "<=":
                return event_value <= value
            elif op == "==":
                return event_value == value
            elif op == "!=":
                return event_value != value
            elif op == "in":
                return event_value in value
            elif op == "contains":
                return value in event_value
            else:
                return False
        
        elif condition["type"] == "group":
            op = condition["op"]
            children = condition.get("children", [])
            
            if op == "AND":
                return all(self._evaluate_condition(child, event) for child in children)
            elif op == "OR":
                return any(self._evaluate_condition(child, event) for child in children)
        
        return False
    
    def _generate_explanation(self, rule: Rule, event: Dict[str, Any]) -> str:
        condition_dsl = json.loads(rule.condition_dsl)
        explanation = f"Rule '{rule.name}' matched because: "
        explanation += self._explain_condition(condition_dsl, event)
        return explanation
    
    def _explain_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> str:
        if condition["type"] == "condition":
            field = condition["field"]
            op = condition["op"]
            value = condition["value"]
            event_value = event.get(field)
            return f"{field} ({event_value}) {op} {value}"
        
        elif condition["type"] == "group":
            op = condition["op"]
            children = condition.get("children", [])
            explanations = [self._explain_condition(child, event) for child in children]
            return f"({f' {op} '.join(explanations)})"
        
        return ""