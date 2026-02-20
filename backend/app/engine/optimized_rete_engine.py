"""
Optimized RETE Engine with true RETE network implementation.

This engine provides:
1. True RETE algorithm for efficient pattern matching (O(1) for shared conditions)
2. Alpha network for individual condition tests
3. Beta network for joining multiple conditions
4. Redis caching for rules
5. Local in-memory caching
6. Thread-safe operation

Usage:
    engine = OptimizedReteEngine(db)
    result = engine.evaluate(event)
"""

from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.utils.redis_client import get_redis_client
from app.config import settings
from app.utils.metrics import (
    increment_events_processed,
    increment_rules_fired,
    observe_processing_time
)
from typing import Dict, Any, List, Optional, Callable
import json
import logging
import hashlib
import time
import threading
from functools import lru_cache

# Import our true RETE network implementation
from app.engine.rete_network import ReteNetwork, ReteEngine as ReteNetworkEngine

logger = logging.getLogger(__name__)

# Flag for RETE availability (always True now with our implementation)
RETE_NETWORK_AVAILABLE = True


class RuleCache:
    """Redis-based rule caching for performance optimization."""
    
    CACHE_KEY_PREFIX = "rule_engine:"
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self):
        self._local_cache: Dict[str, Any] = {}
        self._local_cache_times: Dict[str, float] = {}  # Per-key timestamps
        self._local_cache_ttl = 60  # Local cache for 60 seconds
        self._lock = threading.Lock()
        self._redis_available = False
        self.redis = None
        
        try:
            self.redis = get_redis_client()
            if self.redis is not None:
                self._redis_available = True
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
    
    def _get_cache_key(self, key: str) -> str:
        return f"{self.CACHE_KEY_PREFIX}{key}"
    
    def get_rules(self, db: Session, group: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get rules from cache or database."""
        cache_key = f"rules:{group or 'all'}"
        
        # Check local cache first (fastest)
        if self._is_local_cache_valid(cache_key):
            logger.debug(f"Local cache hit for {cache_key}")
            return self._local_cache.get(cache_key, [])
        
        # Check Redis cache
        if self._redis_available:
            try:
                cached = self.redis.get(self._get_cache_key(cache_key))
                if cached:
                    logger.debug(f"Redis cache hit for {cache_key}")
                    rules = json.loads(cached)
                    self._update_local_cache(cache_key, rules)
                    return rules
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        # Load from database
        logger.debug(f"Cache miss for {cache_key}, loading from database")
        rules = self._load_rules_from_db(db, group)
        
        # Update caches
        self._update_local_cache(cache_key, rules)
        self._update_redis_cache(cache_key, rules)
        
        return rules
    
    def _is_local_cache_valid(self, key: str) -> bool:
        with self._lock:
            if key not in self._local_cache:
                return False
            cache_time = self._local_cache_times.get(key, 0)
            return (time.time() - cache_time) < self._local_cache_ttl
    
    def _update_local_cache(self, key: str, rules: List[Dict[str, Any]]):
        with self._lock:
            self._local_cache[key] = rules
            self._local_cache_times[key] = time.time()
    
    def _update_redis_cache(self, key: str, rules: List[Dict[str, Any]]):
        if self._redis_available:
            try:
                self.redis.setex(
                    self._get_cache_key(key),
                    self.CACHE_TTL,
                    json.dumps(rules)
                )
            except Exception as e:
                logger.warning(f"Failed to update Redis cache: {e}")
    
    def _load_rules_from_db(self, db: Session, group: Optional[str] = None) -> List[Dict[str, Any]]:
        query = db.query(Rule).filter(Rule.enabled == True)
        if group:
            query = query.filter(Rule.group == group)
        query = query.order_by(Rule.priority.desc())
        
        rules = []
        for rule in query.all():
            condition_dsl = rule.condition_dsl
            if isinstance(condition_dsl, str):
                condition_dsl = json.loads(condition_dsl)
            
            rules.append({
                "id": rule.id,
                "name": rule.name,
                "group": rule.group,
                "priority": rule.priority,
                "condition_dsl": condition_dsl,
                "action": rule.action
            })
        
        return rules
    
    def invalidate(self, group: Optional[str] = None):
        """Invalidate cache when rules change."""
        with self._lock:
            self._local_cache.clear()
            self._local_cache_times.clear()
        
        if self._redis_available:
            try:
                if group:
                    self.redis.delete(self._get_cache_key(f"rules:{group}"))
                # Always invalidate the 'all' cache
                self.redis.delete(self._get_cache_key("rules:all"))
                # Invalidate the compiled ruleset hash
                self.redis.delete(self._get_cache_key("ruleset_hash"))
            except Exception as e:
                logger.warning(f"Failed to invalidate cache: {e}")


class ConditionIndex:
    """
    Index conditions by field for faster lookup.
    
    Instead of checking all rules, we first filter by fields present in the event.
    """
    
    def __init__(self):
        self._field_to_rules: Dict[str, List[int]] = {}
        self._rules_by_id: Dict[int, Dict[str, Any]] = {}
    
    def build_index(self, rules: List[Dict[str, Any]]):
        """Build index from list of rules."""
        self._field_to_rules.clear()
        self._rules_by_id.clear()
        
        for rule in rules:
            rule_id = rule["id"]
            self._rules_by_id[rule_id] = rule
            
            # Extract fields from condition_dsl
            fields = self._extract_fields(rule["condition_dsl"])
            for field in fields:
                if field not in self._field_to_rules:
                    self._field_to_rules[field] = []
                self._field_to_rules[field].append(rule_id)
    
    def _extract_fields(self, condition: Dict[str, Any]) -> set:
        """Recursively extract all field names from a condition."""
        fields = set()
        
        if not condition:
            return fields
        
        if condition.get("type") == "condition":
            if condition.get("field"):
                fields.add(condition["field"])
        
        if condition.get("children"):
            for child in condition["children"]:
                fields.update(self._extract_fields(child))
        
        return fields
    
    def get_candidate_rules(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get rules that might match the event based on field presence.
        
        This significantly reduces the number of rules to evaluate
        by only considering rules that check fields present in the event.
        """
        event_fields = set(event.keys())
        candidate_rule_ids = set()
        
        for field in event_fields:
            if field in self._field_to_rules:
                candidate_rule_ids.update(self._field_to_rules[field])
        
        # Also include rules with no specific field requirements (complex rules)
        # These are rules that might have all fields in the event
        
        candidates = [
            self._rules_by_id[rule_id]
            for rule_id in candidate_rule_ids
            if rule_id in self._rules_by_id
        ]
        
        # Sort by priority
        candidates.sort(key=lambda r: r["priority"], reverse=True)
        
        return candidates


class OptimizedReteEngine:
    """
    Main optimized RETE engine with true RETE network implementation.
    
    Strategies used:
    1. Redis caching for rules from database
    2. Local in-memory caching with per-key TTL
    3. True RETE network with alpha/beta nodes for O(1) shared conditions
    4. Thread-safe operation
    5. Comprehensive statistics tracking
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.cache = RuleCache()
        self.rete_engine = ReteNetworkEngine()  # True RETE implementation
        self._index_hash: str = ""  # Track when to rebuild index
        self._lock = threading.Lock()
        self._stats = {
            "total_evaluations": 0,
            "cache_hits": 0,
            "rules_evaluated": 0,
            "rules_matched": 0,
            "avg_evaluation_time_ms": 0,
            "rete_compilations": 0
        }
    
    def evaluate(
        self,
        event: Dict[str, Any],
        rule_ids: Optional[List[int]] = None,
        group: Optional[str] = None,
        use_rete: bool = True
    ) -> Dict[str, Any]:
        """
        Evaluate event against rules using true RETE network.
        
        Args:
            event: The event data to evaluate
            rule_ids: Optional list of specific rule IDs to evaluate
            group: Optional rule group to filter by
            use_rete: Whether to use RETE network (default: True)
        
        Returns:
            Dictionary with matched_rules, execution_order, explanations, and stats
        """
        start_time = time.time()
        
        # Get rules from cache
        rules = self.cache.get_rules(self.db, group)
        
        # Filter by specific rule IDs if provided
        if rule_ids:
            rules = [r for r in rules if r["id"] in rule_ids]
        
        if use_rete:
            # Use true RETE network
            result = self._evaluate_with_rete(event, rules)
        else:
            # Fallback to simple linear evaluation
            result = self._evaluate_simple(event, rules)
        
        # Update stats
        evaluation_time = (time.time() - start_time) * 1000
        evaluation_time_seconds = (time.time() - start_time)
        matched_count = len(result["matched_rules"])
        
        with self._lock:
            self._stats["total_evaluations"] += 1
            n = self._stats["total_evaluations"]
            old_avg = self._stats["avg_evaluation_time_ms"]
            self._stats["avg_evaluation_time_ms"] = old_avg + (evaluation_time - old_avg) / n
            self._stats["rules_matched"] += matched_count
        
        # Update global dashboard metrics
        increment_events_processed()
        if matched_count > 0:
            increment_rules_fired(matched_count)
        observe_processing_time(evaluation_time_seconds)
        
        # Add timing to stats
        result["stats"]["evaluation_time_ms"] = round(evaluation_time, 2)
        
        return result
    
    def _evaluate_with_rete(self, event: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate using the true RETE network.
        
        The RETE network provides:
        - Shared condition evaluation (alpha network)
        - Efficient joins (beta network)
        - O(1) for repeated conditions across rules
        """
        # Load rules into RETE engine (compiles network if needed)
        self.rete_engine.load_rules(rules)
        
        # Evaluate through RETE network
        result = self.rete_engine.evaluate(event)
        
        # Get network stats
        network_stats = self.rete_engine.network.get_stats()
        
        result["stats"]["optimization"] = "rete"
        result["stats"]["alpha_nodes"] = network_stats.get("alpha_nodes", 0)
        result["stats"]["beta_nodes"] = network_stats.get("beta_nodes", 0)
        result["stats"]["shared_conditions"] = network_stats.get("shared_conditions", 0)
        result["stats"]["total_rules"] = len(rules)
        
        return result
    
    def _evaluate_simple(self, event: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fallback simple linear evaluation without RETE."""
        matched_rules = []
        execution_order = []
        explanations = {}
        
        for rule in rules:
            if self._evaluate_condition(rule["condition_dsl"], event):
                matched_rules.append({
                    "id": rule["id"],
                    "name": rule["name"],
                    "priority": rule["priority"],
                    "action": rule["action"]
                })
                execution_order.append(rule["id"])
                explanations[rule["id"]] = self._generate_explanation(rule, event)
        
        return {
            "matched_rules": matched_rules,
            "execution_order": execution_order,
            "explanations": explanations,
            "dry_run": True,
            "stats": {
                "total_rules": len(rules),
                "candidates_evaluated": len(rules),
                "rules_matched": len(matched_rules),
                "optimization": "linear"
            }
        }
    
    def _evaluate_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Evaluate a condition against an event."""
        if not condition:
            return True
        
        condition_type = condition.get("type")
        
        if condition_type == "condition":
            return self._evaluate_simple_condition(condition, event)
        elif condition_type == "group":
            return self._evaluate_group_condition(condition, event)
        
        return False
    
    def _evaluate_simple_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Evaluate a simple field comparison condition."""
        field = condition.get("field")
        op = condition.get("op")
        value = condition.get("value")
        
        event_value = event.get(field)
        if event_value is None:
            return False
        
        try:
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
            elif op == "not_in":
                return event_value not in value
            elif op == "contains":
                return value in event_value
            elif op == "starts_with":
                return str(event_value).startswith(str(value))
            elif op == "ends_with":
                return str(event_value).endswith(str(value))
            elif op == "regex":
                import re
                return bool(re.match(value, str(event_value)))
            else:
                logger.warning(f"Unknown operator: {op}")
                return False
        except Exception as e:
            logger.debug(f"Condition evaluation error: {e}")
            return False
    
    def _evaluate_group_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Evaluate a group condition (AND/OR)."""
        op = condition.get("op", "AND")
        children = condition.get("children", [])
        
        if not children:
            return True
        
        if op == "AND":
            # Short-circuit: return False on first failure
            for child in children:
                if not self._evaluate_condition(child, event):
                    return False
            return True
        elif op == "OR":
            # Short-circuit: return True on first success
            for child in children:
                if self._evaluate_condition(child, event):
                    return True
            return False
        elif op == "NOT":
            # NOT applies to first child only
            if children:
                return not self._evaluate_condition(children[0], event)
            return True
        
        return False
    
    def _generate_explanation(self, rule: Dict[str, Any], event: Dict[str, Any]) -> str:
        """Generate human-readable explanation of why rule matched."""
        explanation = f"Rule '{rule['name']}' matched because: "
        explanation += self._explain_condition(rule["condition_dsl"], event)
        return explanation
    
    def _explain_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> str:
        """Recursively explain condition evaluation."""
        if not condition:
            return "no conditions"
        
        if condition.get("type") == "condition":
            field = condition.get("field", "?")
            op = condition.get("op", "?")
            value = condition.get("value", "?")
            event_value = event.get(field, "undefined")
            return f"{field}={event_value} {op} {value}"
        
        elif condition.get("type") == "group":
            op = condition.get("op", "AND")
            children = condition.get("children", [])
            if not children:
                return "empty group"
            explanations = [self._explain_condition(child, event) for child in children]
            return f"({f' {op} '.join(explanations)})"
        
        return "unknown condition"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine performance statistics."""
        rete_stats = self.rete_engine.get_stats() if self.rete_engine else {}
        return {
            **self._stats,
            "cache_available": self.cache._redis_available,
            "rete_network_available": RETE_NETWORK_AVAILABLE,
            "rete_network": rete_stats.get("network", {})
        }
    
    def reload_rules(self):
        """Reload rules and invalidate cache."""
        self.cache.invalidate()
        self.rete_engine.invalidate()
        logger.info("Rules cache and RETE network invalidated, will reload on next evaluation")
    
    def invalidate_cache(self, group: Optional[str] = None):
        """Invalidate cache for specific group or all groups."""
        self.cache.invalidate(group)
        self.rete_engine.invalidate()
