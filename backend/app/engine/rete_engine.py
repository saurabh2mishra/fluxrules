from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.engine.dsl_parser import DSLParser
from app.engine.profiler import RuleProfiler
from app.config import settings
from app.utils.metrics import (
    increment_events_processed,
    increment_rules_fired,
    observe_processing_time
)
from typing import Dict, Any, List, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Try to import optimized engine
try:
    from app.engine.optimized_rete_engine import OptimizedReteEngine
    OPTIMIZED_ENGINE_AVAILABLE = True
except ImportError:
    OPTIMIZED_ENGINE_AVAILABLE = False
    logger.warning("Optimized RETE engine not available, using simple engine")


class ReteEngine:
    """
    RETE Engine with optional optimization.
    
    If the optimized engine is available, it will be used for better performance.
    Otherwise, falls back to the simple linear evaluation.
    
    Configuration:
        Set USE_OPTIMIZED_ENGINE = True in config/env to use the optimized engine (default)
        Set USE_OPTIMIZED_ENGINE = False to use the simple engine
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.parser = DSLParser()
        self.profiler = RuleProfiler()
        self.rulesets = {}
        
        # Initialize optimized engine if available and enabled
        use_optimized = getattr(settings, 'USE_OPTIMIZED_ENGINE', True)
        if OPTIMIZED_ENGINE_AVAILABLE and use_optimized:
            self._optimized_engine = OptimizedReteEngine(db)
            logger.info("Using optimized RETE engine with caching")
        else:
            self._optimized_engine = None
            logger.info("Using simple RETE engine")
        
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
        
        # Also reload optimized engine cache
        if self._optimized_engine:
            self._optimized_engine.reload_rules()
    
    def simulate(self, event: Dict[str, Any], rule_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Simulate event evaluation against rules.
        
        Uses optimized engine if available, otherwise falls back to simple evaluation.
        """
        # Use optimized engine if available
        if self._optimized_engine:
            return self._optimized_engine.evaluate(event, rule_ids=rule_ids)
        
        # Fallback to simple evaluation
        return self._simple_simulate(event, rule_ids)
    
    def _simple_simulate(self, event: Dict[str, Any], rule_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Original simple simulation logic (kept for fallback)."""
        import time
        start_time = time.time()
        
        rules = self.db.query(Rule).filter(Rule.enabled == True)
        if rule_ids:
            rules = rules.filter(Rule.id.in_(rule_ids))
        rules = rules.order_by(Rule.priority.desc()).all()
        
        total_rules = len(rules)
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
        
        evaluation_time = (time.time() - start_time) * 1000
        evaluation_time_seconds = (time.time() - start_time)
        matched_count = len(matched_rules)
        
        # Update global dashboard metrics
        increment_events_processed()
        if matched_count > 0:
            increment_rules_fired(matched_count)
        observe_processing_time(evaluation_time_seconds)
        
        return {
            "matched_rules": matched_rules,
            "execution_order": execution_order,
            "explanations": explanations,
            "dry_run": True,
            "stats": {
                "total_rules": total_rules,
                "candidates_evaluated": total_rules,
                "rules_matched": matched_count,
                "evaluation_time_ms": round(evaluation_time, 2),
                "optimization": "simple"
            }
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