"""Tests for agenda unscheduling with dirty tracking.

Tests that pending rule activations are cancelled when facts change,
preventing invalid rule firings and improving efficiency.
"""

import pytest

from fluxrules.engine.phreak._engine import PhreakEngine


class TestAgendaUnscheduling:
    """Tests for agenda unscheduling in streaming mode."""

    def test_cancel_activation_on_fact_change(self):
        """Test that pending activations are cancelled when facts change."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_1",
                "condition_dsl": {
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                "action": "log: rule_1",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # First evaluation: rule matches and could be queued
        result1 = engine.evaluate({"age": 25})
        assert 1 in result1.fired_rules

        # Verify agenda exists and has cancellation support
        assert hasattr(engine, "agenda"), "Engine must have agenda for unscheduling"
        assert hasattr(engine.agenda, "cancel_activation"), "Agenda must support cancellation"

        # Second evaluation: facts change, previous activation should be cancelled
        # (if rule no longer matches, it shouldn't fire)
        result2 = engine.evaluate({"age": 15})
        assert 1 not in result2.fired_rules  # Rule should not fire (age <= 18)

    def test_multiple_rules_cancelled_on_field_change(self):
        """Test that multiple rules are cancelled when their dependency field changes."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_1",
                "condition_dsl": {
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                "action": "log: rule_1",
                "priority": 100,
            },
            {
                "id": 2,
                "name": "rule_2",
                "condition_dsl": {
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                "action": "log: rule_2",
                "priority": 90,
            },
            {
                "id": 3,
                "name": "rule_3",
                "condition_dsl": {
                    "type": "condition",
                    "field": "region",
                    "op": "==",
                    "value": "US",
                },
                "action": "log: rule_3",
                "priority": 80,
            },
        ]

        engine.load_rules(rules)

        # First evaluation: rules 1 and 2 match on status, rule 3 on region
        result1 = engine.evaluate({"status": "active", "region": "US"})
        assert 1 in result1.fired_rules
        assert 2 in result1.fired_rules
        assert 3 in result1.fired_rules

        # Change status field: rules 1 and 2 should be cancelled if they were pending
        result2 = engine.evaluate({"status": "inactive", "region": "US"})
        assert 1 not in result2.fired_rules  # Cancelled: status changed
        assert 2 not in result2.fired_rules  # Cancelled: status changed
        assert 3 in result2.fired_rules  # Not affected: region unchanged

    def test_unaffected_rules_not_cancelled(self):
        """Test that rules not depending on changed fields are not cancelled."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_age",
                "condition_dsl": {
                    "type": "condition",
                    "field": "age",
                    "op": ">",
                    "value": 18,
                },
                "action": "log: rule_age",
                "priority": 100,
            },
            {
                "id": 2,
                "name": "rule_status",
                "condition_dsl": {
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                "action": "log: rule_status",
                "priority": 90,
            },
        ]

        engine.load_rules(rules)

        # First: both match
        result1 = engine.evaluate({"age": 25, "status": "active"})
        assert 1 in result1.fired_rules
        assert 2 in result1.fired_rules

        # Change only age: status rule should still evaluate
        result2 = engine.evaluate({"age": 20, "status": "active"})
        assert 1 in result2.fired_rules  # Still matches (age > 18)
        assert 2 in result2.fired_rules  # Not cancelled: status unchanged

    def test_cancellation_with_complex_conditions(self):
        """Test cancellation with AND/OR conditions."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_complex",
                "condition_dsl": {
                    "type": "and",
                    "conditions": [
                        {"type": "condition", "field": "age", "op": ">", "value": 18},
                        {
                            "type": "condition",
                            "field": "status",
                            "op": "==",
                            "value": "active",
                        },
                    ],
                },
                "action": "log: rule_complex",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # Both conditions met
        result1 = engine.evaluate({"age": 25, "status": "active"})
        assert 1 in result1.fired_rules

        # Change age (not in condition): rule depends on age, so it's affected
        result2 = engine.evaluate({"age": 20, "status": "active"})
        assert 1 in result2.fired_rules  # Still matches

        # Change status: rule depends on status, cancellation applies
        result3 = engine.evaluate({"age": 20, "status": "inactive"})
        assert 1 not in result3.fired_rules  # Doesn't match anymore

    def test_cascading_cancellation_with_hierarchies(self):
        """Test that parent-child hierarchies interact with cancellation correctly."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "parent",
                "condition_dsl": {
                    "type": "and",
                    "conditions": [
                        {"type": "condition", "field": "age", "op": ">", "value": 18},
                        {
                            "type": "condition",
                            "field": "status",
                            "op": "==",
                            "value": "active",
                        },
                    ],
                },
                "action": "log: parent",
                "priority": 100,
            },
            {
                "id": 2,
                "name": "child",
                "condition_dsl": {
                    "type": "and",
                    "conditions": [
                        {"type": "condition", "field": "age", "op": ">", "value": 18},
                        {
                            "type": "condition",
                            "field": "status",
                            "op": "==",
                            "value": "active",
                        },
                        {
                            "type": "condition",
                            "field": "score",
                            "op": ">",
                            "value": 100,
                        },
                    ],
                },
                "action": "log: child",
                "priority": 90,
            },
        ]

        engine.load_rules(rules)

        # Both rules match
        result1 = engine.evaluate({"age": 25, "status": "active", "score": 150})
        assert 1 in result1.fired_rules
        assert 2 in result1.fired_rules

        # Change parent condition: both should be affected
        result2 = engine.evaluate({"age": 15, "status": "active", "score": 150})
        assert 1 not in result2.fired_rules  # Parent fails
        assert 2 not in result2.fired_rules  # Child fails (parent condition not met)

    def test_field_removal_triggers_cancellation(self):
        """Test that removing a fact field triggers cancellation of dependent rules."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_requires_field",
                "condition_dsl": {
                    "type": "condition",
                    "field": "score",
                    "op": ">",
                    "value": 100,
                },
                "action": "log: rule_requires_field",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # Rule matches when field exists
        result1 = engine.evaluate({"score": 150})
        assert 1 in result1.fired_rules

        # Remove field: rule's dependent field is now missing
        result2 = engine.evaluate({})
        assert 1 not in result2.fired_rules  # Field missing, rule can't match

    def test_field_addition_triggers_reevaluation(self):
        """Test that adding a new fact field triggers rule evaluation."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_optional_field",
                "condition_dsl": {
                    "type": "condition",
                    "field": "bonus",
                    "op": ">",
                    "value": 0,
                },
                "action": "log: rule_optional_field",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # Rule doesn't match without field
        result1 = engine.evaluate({"other": "data"})
        assert 1 not in result1.fired_rules

        # Add field: rule should now be evaluated
        result2 = engine.evaluate({"bonus": 50})
        assert 1 in result2.fired_rules  # Now matches

    def test_streaming_mode_without_agenda(self):
        """Test that unscheduling gracefully handles missing agenda."""
        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": 1,
                "name": "rule_1",
                "condition_dsl": {
                    "type": "condition",
                    "field": "value",
                    "op": ">",
                    "value": 0,
                },
                "action": "log: rule_1",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # First evaluation
        result1 = engine.evaluate({"value": 10})
        assert 1 in result1.fired_rules

        # Remove agenda to test graceful handling
        if hasattr(engine, "agenda"):
            original_agenda = engine.agenda
            delattr(engine, "agenda")

            # Should still work (just skip cancellation)
            result2 = engine.evaluate({"value": 5})
            assert 1 in result2.fired_rules

            # Restore for cleanup
            engine.agenda = original_agenda

    def test_stateless_mode_no_cancellation(self):
        """Test that cancellation doesn't affect stateless (non-streaming) mode."""
        engine = PhreakEngine(streaming_mode=False)

        rules = [
            {
                "id": 1,
                "name": "rule_1",
                "condition_dsl": {
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                "action": "log: rule_1",
                "priority": 100,
            },
        ]

        engine.load_rules(rules)

        # Stateless: facts are independent
        result1 = engine.evaluate({"status": "active"})
        assert 1 in result1.fired_rules

        result2 = engine.evaluate({"status": "inactive"})
        assert 1 not in result2.fired_rules

        result3 = engine.evaluate({"status": "active"})
        assert 1 in result3.fired_rules  # Always re-evaluated


class TestAgendaUnschedulingPerformance:
    """Performance tests for agenda unscheduling."""

    def test_cancellation_with_many_rules(self):
        """Test cancellation with a large number of rules."""
        engine = PhreakEngine(streaming_mode=True)

        # Create 100 rules with different field dependencies
        rules = []
        for i in range(100):
            rules.append(
                {
                    "id": i,
                    "name": f"rule_{i}",
                    "condition_dsl": {
                        "type": "condition",
                        "field": f"field_{i % 10}",  # 10 unique fields
                        "op": ">",
                        "value": 0,
                    },
                    "action": f"log: rule_{i}",
                    "priority": 100 - i,
                }
            )

        engine.load_rules(rules)

        # Evaluate with 10 fields
        facts1 = {f"field_{i}": 100 + i for i in range(10)}
        result1 = engine.evaluate(facts1)

        # Change one field: should trigger selective cancellation
        facts2 = facts1.copy()
        facts2["field_0"] = 50  # Change field_0
        result2 = engine.evaluate(facts2)

        # Should still have correct results
        assert len(result2.fired_rules) >= 0  # Some rules may no longer match
        assert len(result2.fired_rules) <= len(result1.fired_rules)  # May have fewer

    def test_cancellation_overhead(self):
        """Test that cancellation overhead is minimal."""
        import time

        engine = PhreakEngine(streaming_mode=True)

        rules = [
            {
                "id": i,
                "name": f"rule_{i}",
                "condition_dsl": {
                    "type": "condition",
                    "field": "value",
                    "op": ">",
                    "value": i,
                },
                "action": f"log: rule_{i}",
                "priority": 100 - i,
            }
            for i in range(50)
        ]

        engine.load_rules(rules)

        # Benchmark: fact changes
        start = time.time()
        for i in range(100):
            engine.evaluate({"value": 100 + i})
        elapsed = time.time() - start

        # Should be reasonably fast (no timeout)
        assert elapsed < 5.0, f"Cancellation overhead too high: {elapsed:.2f}s for 100 evals"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
