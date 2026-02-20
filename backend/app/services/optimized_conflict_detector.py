"""
Optimized Conflict Detector
Uses indexed queries and caching for fast conflict detection.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate
from typing import List, Dict, Any, Optional
import json
import hashlib
from functools import lru_cache
import threading
import time


class ConflictCache:
    """Simple in-memory cache for conflict detection data."""
    
    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self._ttl:
                    return self._cache[key]
                else:
                    del self._cache[key]
                    del self._timestamps[key]
        return None
    
    def set(self, key: str, value: Any):
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def invalidate(self, pattern: Optional[str] = None):
        with self._lock:
            if pattern is None:
                self._cache.clear()
                self._timestamps.clear()
            else:
                keys_to_delete = [k for k in self._cache if pattern in k]
                for key in keys_to_delete:
                    del self._cache[key]
                    del self._timestamps[key]


# Global cache instance
_conflict_cache = ConflictCache(ttl_seconds=30)


def invalidate_conflict_cache():
    """Call this when rules are modified."""
    _conflict_cache.invalidate()


class OptimizedConflictDetector:
    """
    Optimized conflict detector that uses:
    1. Indexed database queries instead of loading all rules
    2. Caching for repeated checks
    3. Hash-based condition comparison
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def _hash_condition(self, condition: Any) -> str:
        """Create a hash of the condition for fast comparison."""
        condition_str = json.dumps(condition, sort_keys=True)
        return hashlib.md5(condition_str.encode()).hexdigest()
    
    def check_new_rule_conflicts(self, new_rule: RuleCreate) -> List[Dict[str, Any]]:
        """
        Check if a new rule would conflict with existing rules.
        Uses indexed queries for O(1) priority collision checks.
        """
        conflicts = []
        
        # 1. Check priority collision using indexed query (fast!)
        new_group = new_rule.group or "default"
        priority_conflict = self.db.query(Rule).filter(
            and_(
                Rule.enabled == True,
                Rule.group == new_group,
                Rule.priority == new_rule.priority
            )
        ).first()
        
        if priority_conflict:
            conflicts.append({
                "type": "priority_collision",
                "existing_rule_id": priority_conflict.id,
                "existing_rule_name": priority_conflict.name,
                "group": new_group,
                "priority": new_rule.priority,
                "description": f"Rule '{priority_conflict.name}' (ID: {priority_conflict.id}) has same priority {new_rule.priority} in group '{new_group}'"
            })
        
        # 2. Check for duplicate conditions (using hash for speed)
        new_condition_hash = self._hash_condition(new_rule.condition_dsl)
        
        # Get cached condition hashes or build them
        cache_key = "condition_hashes"
        condition_map = _conflict_cache.get(cache_key)
        
        if condition_map is None:
            # Build condition hash map (only for enabled rules)
            condition_map = {}
            enabled_rules = self.db.query(Rule.id, Rule.name, Rule.condition_dsl).filter(
                Rule.enabled == True
            ).all()
            
            for rule_id, rule_name, condition_dsl in enabled_rules:
                try:
                    if isinstance(condition_dsl, str):
                        condition = json.loads(condition_dsl)
                    else:
                        condition = condition_dsl
                    rule_hash = self._hash_condition(condition)
                    condition_map[rule_hash] = {"id": rule_id, "name": rule_name}
                except:
                    continue
            
            _conflict_cache.set(cache_key, condition_map)
        
        # Check if new condition hash exists
        if new_condition_hash in condition_map:
            existing = condition_map[new_condition_hash]
            conflicts.append({
                "type": "duplicate_condition",
                "existing_rule_id": existing["id"],
                "existing_rule_name": existing["name"],
                "description": f"Identical condition exists in rule '{existing['name']}' (ID: {existing['id']})"
            })
        
        return conflicts
    
    def check_update_rule_conflicts(self, rule_id: int, updated_rule: RuleUpdate) -> List[Dict[str, Any]]:
        """Check if updating a rule would cause conflicts."""
        conflicts = []
        
        current_rule = self.db.query(Rule).filter(Rule.id == rule_id).first()
        if not current_rule:
            return []
        
        # Get updated values
        new_priority = updated_rule.priority if updated_rule.priority is not None else current_rule.priority
        new_group = updated_rule.group if updated_rule.group is not None else (current_rule.group or "default")
        
        # 1. Check priority collision (excluding self)
        if updated_rule.priority is not None or updated_rule.group is not None:
            priority_conflict = self.db.query(Rule).filter(
                and_(
                    Rule.enabled == True,
                    Rule.id != rule_id,
                    Rule.group == new_group,
                    Rule.priority == new_priority
                )
            ).first()
            
            if priority_conflict:
                conflicts.append({
                    "type": "priority_collision",
                    "existing_rule_id": priority_conflict.id,
                    "existing_rule_name": priority_conflict.name,
                    "group": new_group,
                    "priority": new_priority,
                    "description": f"Rule '{priority_conflict.name}' (ID: {priority_conflict.id}) has same priority {new_priority} in group '{new_group}'"
                })
        
        # 2. Check duplicate conditions if condition is being updated
        if updated_rule.condition_dsl is not None:
            new_condition_hash = self._hash_condition(updated_rule.condition_dsl)
            
            # Check against all other rules
            other_rules = self.db.query(Rule.id, Rule.name, Rule.condition_dsl).filter(
                and_(
                    Rule.enabled == True,
                    Rule.id != rule_id
                )
            ).all()
            
            for other_id, other_name, condition_dsl in other_rules:
                try:
                    if isinstance(condition_dsl, str):
                        condition = json.loads(condition_dsl)
                    else:
                        condition = condition_dsl
                    other_hash = self._hash_condition(condition)
                    
                    if new_condition_hash == other_hash:
                        conflicts.append({
                            "type": "duplicate_condition",
                            "existing_rule_id": other_id,
                            "existing_rule_name": other_name,
                            "description": f"Identical condition exists in rule '{other_name}' (ID: {other_id})"
                        })
                        break  # Only report first duplicate
                except:
                    continue
        
        return conflicts
    
    def detect_all_conflicts(self) -> Dict[str, Any]:
        """Detect all conflicts among existing rules."""
        conflicts = []
        
        # Get all enabled rules (only needed columns)
        rules = self.db.query(
            Rule.id, Rule.name, Rule.group, Rule.priority, Rule.condition_dsl
        ).filter(Rule.enabled == True).all()
        
        # Build indexes for fast lookup
        priority_index: Dict[str, Dict[int, List]] = {}  # group -> priority -> [rules]
        condition_index: Dict[str, List] = {}  # hash -> [rules]
        
        for rule_id, name, group, priority, condition_dsl in rules:
            group_key = group or "default"
            
            # Priority index
            if group_key not in priority_index:
                priority_index[group_key] = {}
            if priority not in priority_index[group_key]:
                priority_index[group_key][priority] = []
            priority_index[group_key][priority].append({"id": rule_id, "name": name})
            
            # Condition hash index
            try:
                if isinstance(condition_dsl, str):
                    condition = json.loads(condition_dsl)
                else:
                    condition = condition_dsl
                condition_hash = self._hash_condition(condition)
                
                if condition_hash not in condition_index:
                    condition_index[condition_hash] = []
                condition_index[condition_hash].append({"id": rule_id, "name": name})
            except:
                continue
        
        # Find priority collisions
        for group, priorities in priority_index.items():
            for priority, rules_list in priorities.items():
                if len(rules_list) > 1:
                    for i, rule1 in enumerate(rules_list):
                        for rule2 in rules_list[i+1:]:
                            conflicts.append({
                                "type": "priority_collision",
                                "rule1_id": rule1["id"],
                                "rule1_name": rule1["name"],
                                "rule2_id": rule2["id"],
                                "rule2_name": rule2["name"],
                                "group": group,
                                "priority": priority,
                                "description": f"Rules '{rule1['name']}' and '{rule2['name']}' have same priority {priority} in group '{group}'"
                            })
        
        # Find duplicate conditions
        for condition_hash, rules_list in condition_index.items():
            if len(rules_list) > 1:
                for i, rule1 in enumerate(rules_list):
                    for rule2 in rules_list[i+1:]:
                        conflicts.append({
                            "type": "duplicate_condition",
                            "rule1_id": rule1["id"],
                            "rule1_name": rule1["name"],
                            "rule2_id": rule2["id"],
                            "rule2_name": rule2["name"],
                            "description": f"Rules '{rule1['name']}' (ID: {rule1['id']}) and '{rule2['name']}' (ID: {rule2['id']}) have identical conditions"
                        })
        
        return {"conflicts": conflicts}
