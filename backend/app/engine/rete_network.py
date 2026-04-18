"""
True RETE Network Implementation for Rule Engine.

The RETE algorithm builds a discrimination network where:
1. Alpha Network: Tests individual conditions (field comparisons)
2. Beta Network: Joins results from multiple conditions
3. Terminal Nodes: Fire when all conditions for a rule are satisfied

Benefits:
- Shared condition evaluation across rules
- Incremental updates - only re-evaluate what changed
- O(RxP) complexity where R=rules, P=patterns (vs O(RxFxC) naive)

Reference: "Rete: A Fast Algorithm for the Many Pattern/Many Object Pattern Match Problem"
           by Charles L. Forgy, 1982
"""

from typing import Dict, Any, List, Optional, Set, FrozenSet, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import logging
import hashlib
import threading

from app.config import settings
from app.engine.comparison import evaluate_operator

logger = logging.getLogger(__name__)


class Operator(Enum):
    """Supported comparison operators."""
    EQ = "=="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


@dataclass
class AlphaCondition:
    """
    A single condition test (e.g., amount > 1000).
    
    This is the atomic unit of the alpha network.
    """
    field: str
    operator: Operator
    value: Any
    
    def __hash__(self):
        # Make hashable for deduplication
        value_hash = str(self.value) if not isinstance(self.value, (list, dict)) else hashlib.md5(str(self.value).encode()).hexdigest()
        return hash((self.field, self.operator.value, value_hash))
    
    def __eq__(self, other):
        if not isinstance(other, AlphaCondition):
            return False
        return self.field == other.field and self.operator == other.operator and self.value == other.value
    
    def evaluate(self, event: Dict[str, Any]) -> bool:
        """Evaluate this condition against an event."""
        event_value = event.get(self.field)
        
        if self.operator == Operator.EXISTS:
            return self.field in event
        if self.operator == Operator.NOT_EXISTS:
            return self.field not in event
        
        return evaluate_operator(
            self.operator.value,
            event_value,
            self.value,
            field_present=self.field in event,
            strict_null_handling=settings.STRICT_NULL_HANDLING,
            strict_type_comparison=settings.STRICT_TYPE_COMPARISON,
            boolean_string_coercion=settings.BOOLEAN_STRING_COERCION,
        )
    
    def __repr__(self):
        return f"AlphaCondition({self.field} {self.operator.value} {self.value})"


@dataclass
class AlphaNode:
    """
    Alpha node in the RETE network.
    
    Tests a single condition and propagates matching events to successors.
    Each unique condition has exactly one alpha node (sharing).
    """
    condition: AlphaCondition
    successors: List['BetaNode'] = field(default_factory=list)
    
    # Cache for alpha memory (events that passed this condition)
    alpha_memory: Set[int] = field(default_factory=set)  # Event hashes
    
    def activate(self, event: Dict[str, Any], event_hash: int) -> bool:
        """
        Test event against this node's condition.
        
        Returns True if condition passes.
        """
        result = self.condition.evaluate(event)
        if result:
            self.alpha_memory.add(event_hash)
        return result
    
    def clear_memory(self):
        """Clear alpha memory (for new evaluation cycle)."""
        self.alpha_memory.clear()


@dataclass
class BetaNode:
    """
    Beta node in the RETE network.

    Joins results from multiple alpha nodes (for AND conditions)
    or represents custom evaluator-backed behavior.
    """
    join_type: str = "AND"  # "AND" or "OR"
    parent_alphas: List[AlphaNode] = field(default_factory=list)
    parent_betas: List['BetaNode'] = field(default_factory=list)
    children: List['BetaNode'] = field(default_factory=list)
    terminal: Optional['TerminalNode'] = None
    is_negated: bool = False  # For NOT conditions
    stateful: bool = False
    evaluator: Optional[Callable[[Dict[str, Any], int, Dict[int, bool], 'BetaNode'], bool]] = None
    node_type: str = "standard"
    correlate_field: Optional[str] = None
    
    # Beta memory: stores joined results
    beta_memory: bool = False
    tuple_memory: Dict[str, Set[Any]] = field(default_factory=dict)
    
    def evaluate(
        self,
        event: Dict[str, Any],
        event_hash: int,
        alpha_results: Dict[int, bool],
        stateless_mode: bool = False,
    ) -> bool:
        """
        Evaluate this beta node based on parent results or a custom evaluator.
        """
        if stateless_mode and self.stateful:
            self.beta_memory = False
            return False

        if self.evaluator is not None:
            result = bool(self.evaluator(event, event_hash, alpha_results, self))
        else:
            results = []

            # Get results from parent alpha nodes
            for alpha in self.parent_alphas:
                alpha_id = id(alpha)
                if alpha_id in alpha_results:
                    results.append(alpha_results[alpha_id])
                else:
                    results.append(False)

            # Get results from parent beta nodes
            for beta in self.parent_betas:
                results.append(beta.beta_memory)

            if not results:
                result = True  # Empty condition = always true
            elif self.join_type == "AND":
                result = all(results)
            elif self.join_type == "OR":
                result = any(results)
            else:
                result = False

        if self.is_negated:
            result = not result

        self.beta_memory = result
        return result

    def clear_memory(self):
        """Clear beta memory."""
        if not self.stateful:
            self.beta_memory = False
            self.tuple_memory.clear()
            return

        self.tuple_memory.clear()
        self.beta_memory = False

    def add_tuple(self, correlation_key: str, fact_ids: Any) -> bool:
        """Add a tuple to stateful memory.

        Returns True if tuple is newly inserted.
        """
        if not self.stateful:
            return False

        memory = self.tuple_memory.setdefault(correlation_key, set())
        original_size = len(memory)
        memory.add(fact_ids)
        inserted = len(memory) > original_size
        if inserted:
            self.beta_memory = True
        return inserted

    def remove_tuples_containing(self, fact_id: str) -> int:
        """Remove tuples containing a fact id across all correlation keys.

        Returns the number of removed tuples.
        """
        removed = 0
        empty_keys: List[str] = []

        for correlation_key, tuples_for_key in self.tuple_memory.items():
            to_remove = set()
            for fact_ids in tuples_for_key:
                if isinstance(fact_ids, (set, frozenset, tuple, list)):
                    contains = fact_id in fact_ids
                else:
                    contains = fact_id == fact_ids
                if contains:
                    to_remove.add(fact_ids)
            if to_remove:
                tuples_for_key.difference_update(to_remove)
                removed += len(to_remove)
            if not tuples_for_key:
                empty_keys.append(correlation_key)

        for correlation_key in empty_keys:
            del self.tuple_memory[correlation_key]

        if self.stateful and removed and self.tuple_count() == 0:
            self.beta_memory = False
        return removed

    def tuple_count(self) -> int:
        """Get total tuple count across all correlation keys."""
        return sum(len(tuples_for_key) for tuples_for_key in self.tuple_memory.values())


@dataclass
class TerminalNode:
    """
    Terminal node in the RETE network.
    
    Represents a rule that should fire when its conditions are satisfied.
    """
    rule_id: int
    rule_name: str
    rule_priority: int
    rule_action: str
    rule_data: Dict[str, Any] = field(default_factory=dict)
    is_activated: bool = False
    
    def activate(self):
        """Mark this rule as activated (matched)."""
        self.is_activated = True
    
    def deactivate(self):
        """Reset activation state."""
        self.is_activated = False


class ReteNetwork:
    """
    Complete RETE Network implementation.
    
    The network is built once from rules, then events are passed through
    to determine which rules match.
    """
    
    def __init__(self):
        # Alpha network: condition -> alpha node (shared)
        self._alpha_nodes: Dict[AlphaCondition, AlphaNode] = {}
        
        # Beta network: list of beta nodes for joining
        self._beta_nodes: List[BetaNode] = []
        
        # Terminal nodes: rule_id -> terminal node
        self._terminal_nodes: Dict[int, TerminalNode] = {}
        
        # Root beta node (entry point)
        self._root: Optional[BetaNode] = None
        
        # Field index for fast alpha node lookup
        self._field_to_alphas: Dict[str, List[AlphaNode]] = defaultdict(list)
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Network statistics
        self._stats = {
            "alpha_nodes": 0,
            "beta_nodes": 0,
            "terminal_nodes": 0,
            "shared_conditions": 0
        }
        
        # Compilation hash
        self._rules_hash: str = ""
        
        # Stateful fact and activation tracking for assert/retract flows
        self._fact_id_to_hash: Dict[str, int] = {}
        self._fact_id_to_token: Dict[str, str] = {}
        self._terminal_activations: Dict[int, Set[Tuple[str]]] = defaultdict(set)
    
    def compile(self, rules: List[Dict[str, Any]]) -> bool:
        """
        Compile rules into the RETE network.
        
        This builds the discrimination network from the rule definitions.
        """
        # Calculate hash to check if recompilation needed
        rules_hash = self._calculate_hash(rules)
        if rules_hash == self._rules_hash:
            logger.debug("Rules unchanged, skipping RETE recompilation")
            return True
        
        with self._lock:
            try:
                self._clear_network()
                
                for rule in rules:
                    self._add_rule(rule)
                
                self._rules_hash = rules_hash
                self._update_stats()
                
                logger.info(
                    f"RETE network compiled: {self._stats['alpha_nodes']} alpha nodes, "
                    f"{self._stats['beta_nodes']} beta nodes, "
                    f"{self._stats['terminal_nodes']} terminal nodes, "
                    f"{self._stats['shared_conditions']} shared conditions"
                )
                return True
                
            except Exception as e:
                logger.error(f"Failed to compile RETE network: {e}")
                self._clear_network()
                return False
    
    def _calculate_hash(self, rules: List[Dict[str, Any]]) -> str:
        """Calculate hash of rules for change detection."""
        import json
        rules_str = json.dumps(rules, sort_keys=True, default=str)
        return hashlib.md5(rules_str.encode()).hexdigest()
    
    def _clear_network(self):
        """Clear the entire network."""
        self._alpha_nodes.clear()
        self._beta_nodes.clear()
        self._terminal_nodes.clear()
        self._field_to_alphas.clear()
        self._root = None
        self._rules_hash = ""
        self._fact_id_to_hash.clear()
        self._fact_id_to_token.clear()
        self._terminal_activations.clear()
    
    def _add_rule(self, rule: Dict[str, Any]):
        """Add a single rule to the network."""
        rule_id = rule["id"]
        condition_dsl = rule.get("condition_dsl", {})
        
        # Create terminal node for this rule
        terminal = TerminalNode(
            rule_id=rule_id,
            rule_name=rule.get("name", f"Rule {rule_id}"),
            rule_priority=rule.get("priority", 0),
            rule_action=rule.get("action", ""),
            rule_data=rule
        )
        self._terminal_nodes[rule_id] = terminal
        
        # Build network from condition DSL
        if condition_dsl:
            beta_node = self._build_condition_network(condition_dsl)
            if beta_node:
                beta_node.terminal = terminal
    
    def _build_condition_network(self, condition: Dict[str, Any]) -> Optional[BetaNode]:
        """
        Recursively build the network for a condition.
        
        Returns the beta node that represents this condition.
        """
        condition_type = condition.get("type")
        
        if condition_type == "condition":
            return self._build_alpha_condition(condition)
        if condition_type == "group":
            return self._build_group_condition(condition)
        if condition_type == "accumulate":
            return self._build_accumulate_condition(condition)
        if condition_type == "sequence":
            return self._build_sequence_condition(condition)
        if condition_type == "cross_fact_join":
            return self._build_cross_fact_join_condition(condition)

        logger.warning(f"Unknown condition type: {condition_type}")
        return None
    
    def _build_alpha_condition(self, condition: Dict[str, Any]) -> Optional[BetaNode]:
        """Build network for a simple field condition."""
        field = condition.get("field")
        op_str = condition.get("op")
        value = condition.get("value")
        
        if not field or not op_str:
            return None
        
        # Convert operator string to enum
        try:
            operator = Operator(op_str)
        except ValueError:
            logger.warning(f"Unknown operator: {op_str}")
            return None
        
        # Create or get shared alpha condition
        alpha_condition = AlphaCondition(field=field, operator=operator, value=value)
        
        if alpha_condition in self._alpha_nodes:
            # Reuse existing alpha node (SHARING!)
            self._stats["shared_conditions"] = self._stats.get("shared_conditions", 0) + 1
            alpha_node = self._alpha_nodes[alpha_condition]
        else:
            # Create new alpha node
            alpha_node = AlphaNode(condition=alpha_condition)
            self._alpha_nodes[alpha_condition] = alpha_node
            self._field_to_alphas[field].append(alpha_node)
        
        # Create beta node to hold the result
        beta_node = BetaNode(join_type="AND", parent_alphas=[alpha_node])
        self._beta_nodes.append(beta_node)
        alpha_node.successors.append(beta_node)
        
        return beta_node
    
    def _build_group_condition(self, condition: Dict[str, Any]) -> Optional[BetaNode]:
        """Build network for a group condition (AND/OR/NOT)."""
        op = condition.get("op", "AND").upper()
        children = condition.get("children", [])
        
        if not children:
            # Empty group = always true, create pass-through beta
            beta_node = BetaNode(join_type="AND")
            self._beta_nodes.append(beta_node)
            return beta_node
        
        # Build child networks
        child_betas = []
        for child in children:
            child_beta = self._build_condition_network(child)
            if child_beta:
                child_betas.append(child_beta)
        
        if not child_betas:
            return None
        
        # Handle NOT specially (applies to first child only)
        if op == "NOT":
            if child_betas:
                child_betas[0].is_negated = True
                return child_betas[0]
            return None
        
        # Create join beta node
        beta_node = BetaNode(
            join_type=op,
            parent_betas=child_betas
        )
        self._beta_nodes.append(beta_node)
        
        # Link children to this beta
        for child_beta in child_betas:
            child_beta.children.append(beta_node)
        
        return beta_node
    
    def _evaluate_simple_condition(self, condition: Dict[str, Any], payload: Dict[str, Any]) -> bool:
        """Evaluate a lightweight condition/group definition against a payload."""
        condition_type = condition.get("type", "condition")

        if condition_type == "group":
            op = condition.get("op", "AND").upper()
            children = condition.get("children", [])
            if not children:
                return True
            child_results = [self._evaluate_simple_condition(child, payload) for child in children]
            if op == "AND":
                return all(child_results)
            if op == "OR":
                return any(child_results)
            if op == "NOT":
                return not child_results[0]
            return False

        field = condition.get("field")
        op = condition.get("op")
        if not field or not op:
            return False

        return evaluate_operator(
            op,
            payload.get(field),
            condition.get("value"),
            field_present=field in payload,
            strict_null_handling=settings.STRICT_NULL_HANDLING,
            strict_type_comparison=settings.STRICT_TYPE_COMPARISON,
            boolean_string_coercion=settings.BOOLEAN_STRING_COERCION,
        )

    def _build_accumulate_condition(self, condition: Dict[str, Any]) -> BetaNode:
        """Build evaluator-backed beta node for accumulate conditions."""
        source = condition.get("source")
        field = condition.get("field")
        aggregate = str(condition.get("aggregate", "count")).lower()
        op = condition.get("op", "==")
        threshold = condition.get("value")
        where = condition.get("where")

        def _accumulate_evaluator(event: Dict[str, Any], *_args) -> bool:
            facts = event.get(source, []) if source else []
            if not isinstance(facts, list):
                return False

            filtered = facts
            if where:
                filtered = [fact for fact in facts if isinstance(fact, dict) and self._evaluate_simple_condition(where, fact)]

            if aggregate == "count":
                aggregate_value = len(filtered)
            else:
                numeric_values: List[float] = []
                for fact in filtered:
                    if not isinstance(fact, dict):
                        continue
                    value = fact.get(field)
                    if isinstance(value, (int, float)):
                        numeric_values.append(float(value))
                if aggregate == "sum":
                    aggregate_value = sum(numeric_values)
                elif aggregate == "min":
                    aggregate_value = min(numeric_values) if numeric_values else 0
                elif aggregate == "max":
                    aggregate_value = max(numeric_values) if numeric_values else 0
                elif aggregate == "avg":
                    aggregate_value = (sum(numeric_values) / len(numeric_values)) if numeric_values else 0
                else:
                    return False

            return evaluate_operator(
                op,
                aggregate_value,
                threshold,
                field_present=True,
                strict_null_handling=settings.STRICT_NULL_HANDLING,
                strict_type_comparison=settings.STRICT_TYPE_COMPARISON,
                boolean_string_coercion=settings.BOOLEAN_STRING_COERCION,
            )

        beta_node = BetaNode(join_type="AND", evaluator=_accumulate_evaluator, node_type="accumulate")
        self._beta_nodes.append(beta_node)
        return beta_node

    def _build_sequence_condition(self, condition: Dict[str, Any]) -> BetaNode:
        """Build evaluator-backed beta node for sequence conditions."""
        source = condition.get("source")
        steps = condition.get("steps", [])

        def _sequence_evaluator(event: Dict[str, Any], *_args) -> bool:
            if not isinstance(steps, list) or not steps:
                return False

            facts = event.get(source, []) if source else []
            if not isinstance(facts, list):
                return False

            step_index = 0
            for fact in facts:
                if step_index >= len(steps):
                    break
                if not isinstance(fact, dict):
                    continue
                if self._evaluate_simple_condition(steps[step_index], fact):
                    step_index += 1
            return step_index == len(steps)

        beta_node = BetaNode(join_type="AND", evaluator=_sequence_evaluator, node_type="sequence")
        self._beta_nodes.append(beta_node)
        return beta_node

    def _build_cross_fact_join_condition(self, condition: Dict[str, Any]) -> BetaNode:
        """Build stateful tuple-tracking beta node keyed by correlate field."""
        correlate_field = condition.get("correlate_field")

        def _cross_fact_evaluator(event: Dict[str, Any], event_hash: int, _alpha_results: Dict[int, bool], beta: BetaNode) -> bool:
            key = event.get(correlate_field) if correlate_field else None
            if key is None:
                return False

            fact_token = str(event.get("__fact_token", str(event_hash)))
            tracked_tuple = (fact_token, self._make_hashable(event))
            beta.tuple_memory.setdefault(str(key), set()).add(tracked_tuple)
            return len(beta.tuple_memory[str(key)]) > 1

        beta_node = BetaNode(
            join_type="AND",
            evaluator=_cross_fact_evaluator,
            node_type="cross_fact_join",
            stateful=True,
            correlate_field=correlate_field,
        )
        self._beta_nodes.append(beta_node)
        return beta_node

    def _update_stats(self):
        """Update network statistics."""
        self._stats["alpha_nodes"] = len(self._alpha_nodes)
        self._stats["beta_nodes"] = len(self._beta_nodes)
        self._stats["terminal_nodes"] = len(self._terminal_nodes)
    
    def _make_hashable(self, obj):
        """
        Recursively convert dicts/lists to tuples so the object can be hashed.
        """
        if isinstance(obj, dict):
            return tuple(sorted((k, self._make_hashable(v)) for k, v in obj.items()))
        elif isinstance(obj, list):
            return tuple(self._make_hashable(x) for x in obj)
        else:
            return obj

    def evaluate(self, event: Dict[str, Any]) -> List[TerminalNode]:
        """
        Evaluate an event against the compiled RETE network.
        
        Returns list of terminal nodes (rules) that matched.
        """
        with self._lock:
            # Reset all memories
            self._reset_memories()
            
            # Generate event hash for caching
            event_hash = hash(self._make_hashable(event))
            
            # Phase 1: Alpha Network - evaluate all relevant alpha nodes
            alpha_results: Dict[int, bool] = {}
            event_fields = set(event.keys())
            
            for field in event_fields:
                if field in self._field_to_alphas:
                    for alpha_node in self._field_to_alphas[field]:
                        result = alpha_node.activate(event, event_hash)
                        alpha_results[id(alpha_node)] = result
            
            # Also evaluate alpha nodes for EXISTS/NOT_EXISTS that might not be in event
            for alpha_condition, alpha_node in self._alpha_nodes.items():
                alpha_id = id(alpha_node)
                if alpha_id not in alpha_results:
                    result = alpha_node.activate(event, event_hash)
                    alpha_results[alpha_id] = result
            
            # Phase 2: Beta Network - propagate through joins (bottom-up)
            # We need to evaluate beta nodes in dependency order
            evaluated_betas: Set[int] = set()
            
            def evaluate_beta(beta: BetaNode) -> bool:
                beta_id = id(beta)
                if beta_id in evaluated_betas:
                    return beta.beta_memory
                
                # First evaluate parent betas
                for parent_beta in beta.parent_betas:
                    evaluate_beta(parent_beta)
                
                result = beta.evaluate(event, event_hash, alpha_results, stateless_mode=True)
                evaluated_betas.add(beta_id)
                return result
            
            # Evaluate all beta nodes
            for beta in self._beta_nodes:
                evaluate_beta(beta)
            
            # Phase 3: Collect activated terminal nodes
            matched_terminals: List[TerminalNode] = []
            
            for beta in self._beta_nodes:
                if beta.terminal and beta.beta_memory:
                    beta.terminal.activate()
                    matched_terminals.append(beta.terminal)
            
            # Sort by priority (descending)
            matched_terminals.sort(key=lambda t: t.rule_priority, reverse=True)
            
            return matched_terminals
    
    def _reset_memories(self):
        """Reset all node memories for a new evaluation."""
        for alpha_node in self._alpha_nodes.values():
            alpha_node.clear_memory()
        for beta_node in self._beta_nodes:
            beta_node.clear_memory()
        for terminal in self._terminal_nodes.values():
            terminal.deactivate()
        self._terminal_activations.clear()

    def _run_alpha_phase(self, event: Dict[str, Any], event_hash: int) -> Dict[int, bool]:
        """Run alpha matching and return alpha node results."""
        alpha_results: Dict[int, bool] = {}
        event_fields = set(event.keys())
        
        for field in event_fields:
            if field in self._field_to_alphas:
                for alpha_node in self._field_to_alphas[field]:
                    result = alpha_node.activate(event, event_hash)
                    alpha_results[id(alpha_node)] = result
        
        # Also evaluate alpha nodes for EXISTS/NOT_EXISTS that might not be in event
        for alpha_node in self._alpha_nodes.values():
            alpha_id = id(alpha_node)
            if alpha_id not in alpha_results:
                result = alpha_node.activate(event, event_hash)
                alpha_results[alpha_id] = result
        
        return alpha_results

    def _run_beta_phase(
        self,
        event: Dict[str, Any],
        event_hash: int,
        alpha_results: Dict[int, bool],
        fact_token: str,
    ) -> None:
        """Propagate results through beta nodes."""
        evaluated_betas: Set[int] = set()
        
        def evaluate_beta(beta: BetaNode) -> bool:
            beta_id = id(beta)
            if beta_id in evaluated_betas:
                return beta.beta_memory
            
            for parent_beta in beta.parent_betas:
                evaluate_beta(parent_beta)
            
            result = beta.evaluate(event, event_hash, alpha_results)
            if result and beta.node_type != "cross_fact_join":
                if beta.stateful:
                    beta.add_tuple("__global__", (fact_token,))
                else:
                    beta.tuple_memory.setdefault("__global__", set()).add((fact_token,))
            evaluated_betas.add(beta_id)
            return result
        
        for beta in self._beta_nodes:
            evaluate_beta(beta)

    def _collect_activated_terminals(self, fact_token: str) -> List[TerminalNode]:
        """Collect and track activated terminal nodes."""
        matched_terminals: List[TerminalNode] = []
        
        for beta in self._beta_nodes:
                if beta.terminal and beta.beta_memory:
                    beta.terminal.activate()
                    self._terminal_activations[beta.terminal.rule_id].add((fact_token,))
                    matched_terminals.append(beta.terminal)
        
        matched_terminals.sort(key=lambda t: t.rule_priority, reverse=True)
        return matched_terminals

    def assert_fact(self, fact_id: str, event: Dict[str, Any]) -> List[TerminalNode]:
        """
        Assert a fact into the network without resetting memories.
        
        Returns list of terminal nodes activated by this asserted fact.
        """
        with self._lock:
            event_hash = hash(self._make_hashable(event))
            fact_token = f"{event_hash}:{fact_id}"
            event_with_meta = dict(event)
            event_with_meta["__fact_token"] = fact_token
            self._fact_id_to_hash[fact_id] = event_hash
            self._fact_id_to_token[fact_id] = fact_token
            
            alpha_results = self._run_alpha_phase(event_with_meta, event_hash)
            self._run_beta_phase(event_with_meta, event_hash, alpha_results, fact_token)
            return self._collect_activated_terminals(fact_token)

    def retract_fact(self, fact_id: str, event: Optional[Dict[str, Any]] = None) -> List[TerminalNode]:
        """
        Retract a fact from stateful memories.
        
        Returns terminal activations cancelled by this retraction.
        """
        with self._lock:
            fact_hash = self._fact_id_to_hash.pop(fact_id, None)
            fact_token = self._fact_id_to_token.pop(fact_id, None)
            if fact_hash is None or fact_token is None:
                return []
            
            # Remove fact hash from alpha memories
            for alpha_node in self._alpha_nodes.values():
                alpha_node.alpha_memory.discard(fact_hash)
            
            # Remove tuples from stateful betas
            for beta in self._beta_nodes:
                beta.remove_tuples_containing(fact_token)
                if not beta.tuple_memory:
                    beta.beta_memory = False
            
            # Cancel terminal activations tied to removed fact
            cancelled_map: Dict[int, TerminalNode] = {}
            for terminal in self._terminal_nodes.values():
                active_tuples = self._terminal_activations.get(terminal.rule_id, set())
                to_cancel = {tpl for tpl in active_tuples if fact_token in tpl}
                if not to_cancel:
                    continue
                
                active_tuples.difference_update(to_cancel)
                cancelled_map[terminal.rule_id] = terminal
                if not active_tuples:
                    terminal.deactivate()
            
            return list(cancelled_map.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get network statistics."""
        return {
            **self._stats,
            "compiled": bool(self._rules_hash),
            "rules_hash": self._rules_hash[:8] if self._rules_hash else None
        }
    
    def is_compiled(self) -> bool:
        """Check if the network is compiled."""
        return bool(self._rules_hash)


class ReteEngine:
    """
    High-level RETE Engine with caching and statistics.
    
    This wraps the RETE network with additional features:
    - Rule caching from database
    - Performance statistics
    - Explanation generation
    """
    
    def __init__(self, db=None):
        self.db = db
        self.network = ReteNetwork()
        self._rules_cache: List[Dict[str, Any]] = []
        self._stats = {
            "total_evaluations": 0,
            "total_matches": 0,
            "avg_evaluation_time_ms": 0,
            "cache_compilations": 0
        }
        self._lock = threading.Lock()
    
    def load_rules(self, rules: List[Dict[str, Any]]) -> bool:
        """Load rules and compile the RETE network."""
        with self._lock:
            self._rules_cache = rules
            success = self.network.compile(rules)
            if success:
                self._stats["cache_compilations"] += 1
            return success
    
    def evaluate(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate an event against the rules.
        
        Returns:
            Dictionary with matched_rules, execution_order, explanations, stats
        """
        import time
        start_time = time.time()
        
        # Compile if not already done
        if not self.network.is_compiled() and self._rules_cache:
            self.network.compile(self._rules_cache)
        
        # Evaluate through RETE network
        matched_terminals = self.network.evaluate(event)
        
        # Build response
        matched_rules = []
        execution_order = []
        explanations = {}
        
        for terminal in matched_terminals:
            matched_rules.append({
                "id": terminal.rule_id,
                "name": terminal.rule_name,
                "priority": terminal.rule_priority,
                "action": terminal.rule_action
            })
            execution_order.append(terminal.rule_id)
            explanations[terminal.rule_id] = self._generate_explanation(terminal, event)
        
        # Update stats
        evaluation_time = (time.time() - start_time) * 1000
        self._update_stats(len(matched_rules), evaluation_time)
        
        network_stats = self.network.get_stats()
        
        return {
            "matched_rules": matched_rules,
            "execution_order": execution_order,
            "explanations": explanations,
            "dry_run": True,
            "stats": {
                "total_rules": len(self._rules_cache),
                "rules_matched": len(matched_rules),
                "evaluation_time_ms": round(evaluation_time, 2),
                "optimization": "rete",
                "alpha_nodes": network_stats["alpha_nodes"],
                "beta_nodes": network_stats["beta_nodes"],
                "shared_conditions": network_stats["shared_conditions"]
            }
        }
    
    def _generate_explanation(self, terminal: TerminalNode, event: Dict[str, Any]) -> str:
        """Generate human-readable explanation."""
        rule_data = terminal.rule_data
        condition_dsl = rule_data.get("condition_dsl", {})
        
        explanation = f"Rule '{terminal.rule_name}' matched: "
        explanation += self._explain_condition(condition_dsl, event)
        
        matching_conditions = self._get_matching_conditions(condition_dsl, event)
        if matching_conditions:
            explanation += f" | Matching conditions: {', '.join(matching_conditions)}"
        
        return explanation
    
    def _get_matching_conditions(self, condition: Dict[str, Any], event: Dict[str, Any]) -> List[str]:
        """Get list of conditions that evaluated to True."""
        matching = []
        
        if not condition:
            return matching
        
        condition_type = condition.get("type")
        
        if condition_type == "condition":
            field = condition.get("field", "?")
            op = condition.get("op", "?")
            value = condition.get("value", "?")
            event_value = event.get(field)
            field_present = field in event
            
            if field_present:
                result = self._evaluate_single_condition(op, event_value, value)
                if result:
                    matching.append(f"{field}={event_value} {op} {value}")
        
        elif condition_type == "group":
            children = condition.get("children", [])
            for child in children:
                matching.extend(self._get_matching_conditions(child, event))
        
        return matching
    
    def _evaluate_single_condition(self, op: str, event_value: Any, value: Any) -> bool:
        """Helper to evaluate a single condition using strict comparison semantics."""
        return evaluate_operator(
            op,
            event_value,
            value,
            field_present=True,
            strict_null_handling=settings.STRICT_NULL_HANDLING,
            strict_type_comparison=settings.STRICT_TYPE_COMPARISON,
            boolean_string_coercion=settings.BOOLEAN_STRING_COERCION,
            emit_metrics=False,
        )

    def _explain_condition(self, condition: Dict[str, Any], event: Dict[str, Any]) -> str:
        """Recursively explain condition evaluation with pass/fail indicators."""
        if not condition:
            return "no conditions"
        
        condition_type = condition.get("type")
        
        if condition_type == "condition":
            field = condition.get("field", "?")
            op = condition.get("op", "?")
            value = condition.get("value", "?")
            event_value = event.get(field)
            
            # Determine if condition passed
            if event_value is None:
                # Field not present in event - condition fails
                return f"[✗ {field}=MISSING {op} {value}]"
            else:
                result = self._evaluate_single_condition(op, event_value, value)
                if result:
                    return f"[✓ {field}={event_value} {op} {value}]"
                else:
                    return f"[✗ {field}={event_value} {op} {value}]"
        
        elif condition_type == "group":
            op = condition.get("op", "AND")
            children = condition.get("children", [])
            if not children:
                return "empty group"
            explanations = [self._explain_condition(child, event) for child in children]
            return f"({f' {op} '.join(explanations)})"
        
        return "unknown condition"
    
    def _update_stats(self, matches: int, evaluation_time: float):
        """Update performance statistics."""
        with self._lock:
            self._stats["total_evaluations"] += 1
            self._stats["total_matches"] += matches
            
            # Rolling average
            n = self._stats["total_evaluations"]
            old_avg = self._stats["avg_evaluation_time_ms"]
            self._stats["avg_evaluation_time_ms"] = old_avg + (evaluation_time - old_avg) / n
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            **self._stats,
            "network": self.network.get_stats()
        }
    
    def invalidate(self):
        """Invalidate the compiled network."""
        with self._lock:
            self._rules_cache.clear()
            self.network._clear_network()
