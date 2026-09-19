"""Mixin for lazy evaluation support (PHREAK strategy only).

This mixin is used by PhreakEngine to add dirty tracking, segment identification,
and token propagation. Other engines that don't include this mixin avoid the
associated overhead.

The LazyEvaluationMixin implements the Strategy Pattern: concrete engines
choose which mixins to inherit from, determining their evaluation strategy.

Usage:
    class PhreakEngine(LazyEvaluationMixin, BaseEngine):
        # Gets lazy evaluation capabilities from mixin
        # Gets shared infrastructure from BaseEngine
        pass
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxrules.engine.infrastructure.field_index import FieldIndex
    from fluxrules.engine.infrastructure.global_rule_repository import (
        GlobalRuleRepository,
    )
    from fluxrules.engine.infrastructure.segment_network import SegmentNetwork


class LazyEvaluationMixin:
    """Adds lazy evaluation capabilities to engines that support it.

    This mixin is designed to be used with BaseEngine through multiple
    inheritance (via Python's Method Resolution Order):

        class PhreakEngine(LazyEvaluationMixin, BaseEngine):
            ...

    The MRO will be:
        PhreakEngine → LazyEvaluationMixin → BaseEngine → ABC → object

    Provides:
    - Dirty segment tracking (_prev_facts, _dirty_segments)
    - Field change detection (_identify_dirty_segments)
    - Index building (_build_lazy_indices)

    Note: BaseEngine must provide these attributes for this mixin to work:
        - field_index: FieldIndex instance
        - segment_network: SegmentNetwork instance
        - token_propagator: TokenPropagator instance
        - rule_repository: GlobalRuleRepository instance
    """

    if TYPE_CHECKING:
        field_index: FieldIndex
        segment_network: SegmentNetwork
        rule_repository: GlobalRuleRepository

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize lazy evaluation state.

        Calls super().__init__() to allow proper MRO chain initialization.
        BaseEngine.__init__() will be called via the MRO chain.

        Args:
            *args: Positional arguments passed to next class in MRO
            **kwargs: Keyword arguments passed to next class in MRO
        """
        super().__init__(*args, **kwargs)
        # Track previous facts for dirty segment identification
        self._prev_facts: dict[str, Any] = {}
        # Cache of segments that need re-evaluation (optional, for future optimization)
        self._dirty_segments: set[str] = set()

    def _identify_dirty_segments(self, facts: dict[str, Any]) -> set[str]:
        """Identify segments affected by changed fields.

        Compares current facts to previous evaluation and returns segments
        whose condition fields have changed. This is the key optimization
        for PHREAK: only evaluate rules in affected segments.

        Algorithm:
        1. On first evaluation (_prev_facts is empty), all fields are dirty
        2. Find newly added/removed fields (symmetric difference)
        3. Find fields with changed values (in both facts and prev_facts)
        4. Look up which segments depend on those fields (via FieldIndex)
        5. Return the union of affected segments

        Args:
            facts: Current evaluation facts

        Returns:
            Set of segment IDs that need re-evaluation (empty set if no changes)

        Example:
            >>> engine._prev_facts = {"age": 25, "country": "US"}
            >>> affected = engine._identify_dirty_segments({"age": 30, "country": "US"})
            >>> affected  # Only segments depending on 'age' field
            {'segment_1', 'segment_3'}
        """
        # On first evaluation, treat all fields as dirty
        if not self._prev_facts:
            changed_fields = set(facts.keys())
        else:
            # Find newly added or removed fields
            current_fields = set(facts.keys())
            prev_fields = set(self._prev_facts.keys())
            changed_fields = current_fields ^ prev_fields

            # Find fields with changed values in overlapping fields
            for field in current_fields & prev_fields:
                if facts[field] != self._prev_facts.get(field):
                    changed_fields.add(field)

        # Get segments affected by these field changes
        # field_index._field_to_segments maps field names to segment IDs
        affected_segments: set[str] = set()
        for field in changed_fields:
            # Access internal dict (using underscore since this is framework code)
            field_segments = self.field_index._field_to_segments.get(field, set())
            affected_segments.update(field_segments)

        return affected_segments

    def _update_prev_facts(self, facts: dict[str, Any]) -> None:
        """Update tracked facts after evaluation.

        This is called after evaluation completes to enable dirty segment
        identification in the next evaluation cycle. It's the "memory"
        component of dirty tracking.

        Args:
            facts: Facts from the completed evaluation

        Example:
            >>> engine.evaluate({"amount": 100})
            >>> # Internally calls: engine._update_prev_facts(facts)
            >>> # Next call: engine.evaluate({"amount": 150})
            >>> # Can now see that 'amount' changed
        """
        self._prev_facts = dict(facts)

    def _build_lazy_indices(self, rules: list[Any]) -> None:
        """Build segment network and field index for lazy evaluation.

        This method populates the infrastructure modules (segment_network
        and field_index) that enable lazy evaluation. It should be called
        whenever rules are added to the engine.

        The built indices enable:
        - FieldIndex: Fast lookup of which rules depend on each field
        - SegmentNetwork: Hierarchical organization of rules for efficient propagation

        Args:
            rules: List of Rule objects or rule dicts to index

        Example:
            >>> rules = [rule1, rule2, rule3]
            >>> engine._build_lazy_indices(rules)
            >>> # Now engine.field_index knows which rules use which fields
            >>> # And engine.segment_network is ready for token propagation
        """
        # Add rules to repository (if not already done by caller)
        for rule in rules:
            self.rule_repository.add_rule(rule)

        # Get all rules from repository
        all_rules = list(self.rule_repository.rules.values())

        # Build segment network (hierarchical organization)
        self.segment_network.add_rules(all_rules)

        # Build field index (field → segment mapping)
        self.field_index.build_from_rules(all_rules)
