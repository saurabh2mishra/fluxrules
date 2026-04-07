"""
Tests for the true RETE network implementation.
"""

import pytest
from app.engine.rete_network import (
    ReteNetwork, ReteEngine, AlphaCondition, Operator
)


class TestAlphaCondition:
    """Test individual condition evaluation."""
    
    def test_equality_operator(self):
        cond = AlphaCondition(field="status", operator=Operator.EQ, value="active")
        assert cond.evaluate({"status": "active"}) == True
        assert cond.evaluate({"status": "inactive"}) == False
        assert cond.evaluate({}) == False
    
    def test_greater_than_operator(self):
        cond = AlphaCondition(field="amount", operator=Operator.GT, value=100)
        assert cond.evaluate({"amount": 150}) == True
        assert cond.evaluate({"amount": 100}) == False
        assert cond.evaluate({"amount": 50}) == False
    
    def test_less_than_or_equal_operator(self):
        cond = AlphaCondition(field="age", operator=Operator.LE, value=18)
        assert cond.evaluate({"age": 18}) == True
        assert cond.evaluate({"age": 15}) == True
        assert cond.evaluate({"age": 21}) == False
    
    def test_in_operator(self):
        cond = AlphaCondition(field="country", operator=Operator.IN, value=["US", "UK", "CA"])
        assert cond.evaluate({"country": "US"}) == True
        assert cond.evaluate({"country": "FR"}) == False
    
    def test_contains_operator(self):
        cond = AlphaCondition(field="email", operator=Operator.CONTAINS, value="@gmail")
        assert cond.evaluate({"email": "user@gmail.com"}) == True
        assert cond.evaluate({"email": "user@yahoo.com"}) == False
    
    def test_regex_operator(self):
        cond = AlphaCondition(field="phone", operator=Operator.REGEX, value=r"^\d{3}-\d{4}$")
        assert cond.evaluate({"phone": "123-4567"}) == True
        assert cond.evaluate({"phone": "1234567"}) == False
    
    def test_exists_operator(self):
        cond = AlphaCondition(field="optional_field", operator=Operator.EXISTS, value=None)
        assert cond.evaluate({"optional_field": "value"}) == True
        assert cond.evaluate({}) == False
    
    def test_not_exists_operator(self):
        cond = AlphaCondition(field="banned_field", operator=Operator.NOT_EXISTS, value=None)
        assert cond.evaluate({}) == True
        assert cond.evaluate({"banned_field": "exists"}) == False


class TestReteNetwork:
    """Test the RETE network compilation and evaluation."""
    
    def test_single_rule_compilation(self):
        network = ReteNetwork()
        rules = [{
            "id": 1,
            "name": "High Value",
            "priority": 10,
            "action": "alert",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 1000
            }
        }]
        
        assert network.compile(rules) == True
        stats = network.get_stats()
        assert stats["alpha_nodes"] == 1
        assert stats["terminal_nodes"] == 1
    
    def test_shared_conditions(self):
        """Test that identical conditions share alpha nodes."""
        network = ReteNetwork()
        rules = [
            {
                "id": 1,
                "name": "Rule 1",
                "priority": 10,
                "action": "action1",
                "condition_dsl": {
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 1000
                }
            },
            {
                "id": 2,
                "name": "Rule 2",
                "priority": 5,
                "action": "action2",
                "condition_dsl": {
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 1000  # Same condition!
                }
            }
        ]
        
        assert network.compile(rules) == True
        stats = network.get_stats()
        # Should only have 1 alpha node because condition is shared
        assert stats["alpha_nodes"] == 1
        assert stats["shared_conditions"] >= 1
        assert stats["terminal_nodes"] == 2
    
    def test_and_condition_group(self):
        network = ReteNetwork()
        rules = [{
            "id": 1,
            "name": "Fraud Detection",
            "priority": 10,
            "action": "block",
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 10000},
                    {"type": "condition", "field": "country", "op": "==", "value": "NG"}
                ]
            }
        }]
        
        assert network.compile(rules) == True
        
        # Should match: high amount AND country is NG
        matched = network.evaluate({"amount": 15000, "country": "NG"})
        assert len(matched) == 1
        assert matched[0].rule_id == 1
        
        # Should NOT match: high amount but wrong country
        matched = network.evaluate({"amount": 15000, "country": "US"})
        assert len(matched) == 0
        
        # Should NOT match: right country but low amount
        matched = network.evaluate({"amount": 500, "country": "NG"})
        assert len(matched) == 0
    
    def test_or_condition_group(self):
        network = ReteNetwork()
        rules = [{
            "id": 1,
            "name": "VIP Detection",
            "priority": 10,
            "action": "upgrade",
            "condition_dsl": {
                "type": "group",
                "op": "OR",
                "children": [
                    {"type": "condition", "field": "tier", "op": "==", "value": "gold"},
                    {"type": "condition", "field": "spend", "op": ">", "value": 10000}
                ]
            }
        }]
        
        assert network.compile(rules) == True
        
        # Should match: gold tier
        matched = network.evaluate({"tier": "gold", "spend": 100})
        assert len(matched) == 1
        
        # Should match: high spend
        matched = network.evaluate({"tier": "bronze", "spend": 15000})
        assert len(matched) == 1
        
        # Should NOT match: neither condition
        matched = network.evaluate({"tier": "bronze", "spend": 100})
        assert len(matched) == 0
    
    def test_nested_groups(self):
        network = ReteNetwork()
        rules = [{
            "id": 1,
            "name": "Complex Rule",
            "priority": 10,
            "action": "complex_action",
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "type", "op": "==", "value": "transfer"},
                    {
                        "type": "group",
                        "op": "OR",
                        "children": [
                            {"type": "condition", "field": "amount", "op": ">", "value": 10000},
                            {"type": "condition", "field": "risk_score", "op": ">", "value": 80}
                        ]
                    }
                ]
            }
        }]
        
        assert network.compile(rules) == True
        
        # Should match: transfer AND high amount
        matched = network.evaluate({"type": "transfer", "amount": 15000, "risk_score": 50})
        assert len(matched) == 1
        
        # Should match: transfer AND high risk
        matched = network.evaluate({"type": "transfer", "amount": 500, "risk_score": 90})
        assert len(matched) == 1
        
        # Should NOT match: not a transfer
        matched = network.evaluate({"type": "payment", "amount": 15000, "risk_score": 90})
        assert len(matched) == 0
    
    def test_priority_ordering(self):
        """Test that matched rules are returned in priority order."""
        network = ReteNetwork()
        rules = [
            {
                "id": 1,
                "name": "Low Priority",
                "priority": 1,
                "action": "low",
                "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 100}
            },
            {
                "id": 2,
                "name": "High Priority",
                "priority": 100,
                "action": "high",
                "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 100}
            },
            {
                "id": 3,
                "name": "Medium Priority",
                "priority": 50,
                "action": "medium",
                "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 100}
            }
        ]
        
        network.compile(rules)
        matched = network.evaluate({"amount": 500})
        
        assert len(matched) == 3
        assert matched[0].rule_priority == 100
        assert matched[1].rule_priority == 50
        assert matched[2].rule_priority == 1


class TestReteEngine:
    """Test the high-level RETE engine."""
    
    def test_engine_evaluate(self):
        engine = ReteEngine()
        rules = [{
            "id": 1,
            "name": "Test Rule",
            "priority": 10,
            "action": "test_action",
            "condition_dsl": {
                "type": "condition",
                "field": "status",
                "op": "==",
                "value": "active"
            }
        }]
        
        engine.load_rules(rules)
        result = engine.evaluate({"status": "active"})
        
        assert len(result["matched_rules"]) == 1
        assert result["matched_rules"][0]["name"] == "Test Rule"
        assert result["stats"]["optimization"] == "rete"
        assert "evaluation_time_ms" in result["stats"]
    
    def test_engine_explanations(self):
        engine = ReteEngine()
        rules = [{
            "id": 1,
            "name": "Amount Check",
            "priority": 10,
            "action": "alert",
            "condition_dsl": {
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 1000
            }
        }]
        
        engine.load_rules(rules)
        result = engine.evaluate({"amount": 5000})
        
        assert 1 in result["explanations"]
        explanation = result["explanations"][1]
        assert "amount" in explanation
        assert "5000" in explanation
    
    def test_engine_stats(self):
        engine = ReteEngine()
        rules = [{
            "id": 1,
            "name": "Test",
            "priority": 10,
            "action": "test",
            "condition_dsl": {"type": "condition", "field": "x", "op": "==", "value": 1}
        }]
        
        engine.load_rules(rules)
        
        # Run multiple evaluations
        for i in range(5):
            engine.evaluate({"x": 1})
        
        stats = engine.get_stats()
        assert stats["total_evaluations"] == 5
        assert stats["total_matches"] == 5
        assert stats["avg_evaluation_time_ms"] > 0


class TestPerformance:
    """Performance tests for the RETE network."""
    
    def test_many_rules_shared_conditions(self):
        """Test performance with many rules sharing conditions."""
        import time
        
        network = ReteNetwork()
        
        # Create 1000 rules, many sharing conditions
        rules = []
        for i in range(1000):
            # Groups of 10 rules share the same condition
            threshold = (i // 10) * 100
            rules.append({
                "id": i,
                "name": f"Rule {i}",
                "priority": i,
                "action": f"action_{i}",
                "condition_dsl": {
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": threshold
                }
            })
        
        start = time.time()
        network.compile(rules)
        compile_time = time.time() - start
        
        stats = network.get_stats()
        
        # Should have ~100 unique alpha nodes (1000 rules / 10 per group)
        assert stats["alpha_nodes"] <= 100
        assert stats["shared_conditions"] >= 900  # Most conditions shared
        
        # Compilation should be fast
        assert compile_time < 1.0  # Under 1 second
        
        # Evaluation should be fast
        start = time.time()
        matched = network.evaluate({"amount": 50000})
        eval_time = time.time() - start
        
        assert eval_time < 0.1  # Under 100ms
        assert len(matched) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
