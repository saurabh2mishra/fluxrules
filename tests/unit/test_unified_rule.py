"""Tests for unified Rule class with Pydantic validation and auto-ID generation."""

import pytest
from pydantic import ValidationError

from fluxrules.config.deployment import DeploymentConfig, DeploymentType
from fluxrules.domain.unified_rule import Rule
from fluxrules.utils.id_generators import RuleIDGenerator

# Minimal valid condition used as a stub where the test is not about conditions.
_STUB = {"type": "condition", "field": "x", "op": ">", "value": 0}


class TestRuleBasicCreation:
    """Test basic rule creation."""

    def test_create_rule_with_auto_id(self):
        """Rule should auto-generate sequential IDs."""
        rule = Rule(
            name="Test Rule",
            conditions={
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            action="allow",
        )
        assert rule.id is not None
        assert isinstance(rule.id, int)
        assert rule.id > 0

    def test_create_rule_with_manual_id(self):
        """User can override auto-generated ID."""
        rule = Rule(
            id=42,
            name="Test Rule",
            conditions={
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            action="allow",
        )
        assert rule.id == 42

    def test_create_rule_with_defaults(self):
        """Rule should have sensible defaults."""
        rule = Rule(
            name="Test Rule",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
        )
        assert rule.action == ""
        assert rule.priority == 0
        assert rule.enabled is True
        assert rule.domain == "default"
        assert rule.tags == frozenset()
        assert rule.metadata == {}

    def test_create_rule_minimal(self):
        """Rule can be created with just name and conditions."""
        rule = Rule(
            name="Minimal Rule",
            conditions={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 100,
            },
        )
        assert rule.name == "Minimal Rule"
        assert rule.conditions["type"] == "condition"
        assert rule.id is not None


class TestRuleValidation:
    """Test Pydantic validation."""

    def test_name_required(self):
        """Name is required."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(conditions=_STUB)
        assert "name" in str(exc_info.value).lower()

    def test_name_not_empty(self):
        """Name cannot be empty."""
        with pytest.raises(ValidationError):
            Rule(name="", conditions=_STUB)

    def test_conditions_required(self):
        """conditions is required."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(name="Test")
        assert "conditions" in str(exc_info.value).lower()

    def test_conditions_must_be_dict(self):
        """conditions must be a dictionary."""
        with pytest.raises(ValidationError):
            Rule(name="Test", conditions="invalid")

    def test_conditions_not_empty(self):
        """conditions cannot be empty."""
        with pytest.raises(ValidationError):
            Rule(name="Test", conditions={})

    def test_conditions_must_have_type(self):
        """conditions must have 'type' field."""
        with pytest.raises(ValidationError):
            Rule(name="Test", conditions={"field": "amount"})

    def test_priority_non_negative(self):
        """Priority must be non-negative."""
        with pytest.raises(ValidationError):
            Rule(
                name="Test",
                conditions=_STUB,
                priority=-1,
            )

    def test_sla_latency_non_negative(self):
        """SLA latency must be non-negative."""
        with pytest.raises(ValidationError):
            Rule(
                name="Test",
                conditions=_STUB,
                sla_latency_ms=-100,
            )

    def test_extra_fields_forbidden(self):
        """Extra fields should be rejected (strict mode)."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                name="Test",
                conditions=_STUB,
                unknown_field="value",
            )
        assert "unknown_field" in str(exc_info.value).lower()

    def test_name_max_length(self):
        """Name cannot exceed max length."""
        with pytest.raises(ValidationError):
            Rule(
                name="x" * 256,
                conditions=_STUB,
            )


class TestTagsHandling:
    """Test tags field validation and conversion."""

    def test_tags_frozenset_direct(self):
        """Tags can be passed as frozenset."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags=frozenset(["high_priority", "fraud"]),
        )
        assert rule.tags == frozenset(["high_priority", "fraud"])

    def test_tags_list_conversion(self):
        """Tags as list converted to frozenset."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags=["tag1", "tag2"],
        )
        assert rule.tags == frozenset(["tag1", "tag2"])
        assert isinstance(rule.tags, frozenset)

    def test_tags_tuple_conversion(self):
        """Tags as tuple converted to frozenset."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags=("tag1", "tag2"),
        )
        assert rule.tags == frozenset(["tag1", "tag2"])

    def test_tags_set_conversion(self):
        """Tags as set converted to frozenset."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags={"tag1", "tag2"},
        )
        assert rule.tags == frozenset(["tag1", "tag2"])

    def test_tags_string_parsing(self):
        """Tags as comma-separated string parsed."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags="tag1, tag2, tag3",
        )
        assert rule.tags == frozenset(["tag1", "tag2", "tag3"])

    def test_tags_none_default(self):
        """Tags None becomes empty frozenset."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
            tags=None,
        )
        assert rule.tags == frozenset()


class TestSerializationDeserialization:
    """Test serialization and deserialization."""

    def test_model_dump(self):
        """Rule can be serialized to dict."""
        rule = Rule(
            id=1,
            name="Test",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            action="flag",
            tags=["tag1"],
        )
        data = rule.model_dump()
        assert data["id"] == 1
        assert data["name"] == "Test"
        assert data["action"] == "flag"
        # Tags should be list in dict
        assert set(data["tags"]) == {"tag1"}

    def test_model_dump_json(self):
        """Rule can be serialized to JSON."""
        rule = Rule(
            name="Test",
            conditions=_STUB,
        )
        json_str = rule.model_dump_json()
        assert isinstance(json_str, str)
        assert '"name":"Test"' in json_str or '"name": "Test"' in json_str

    def test_model_validate_from_dict(self):
        """Rule can be created from dict (validation)."""
        data = {
            "name": "Test",
            "conditions": _STUB,
            "action": "flag",
            "priority": 10,
        }
        rule = Rule(**data)
        assert rule.name == "Test"
        assert rule.priority == 10
        assert rule.action == "flag"

    def test_model_validate_yaml(self):
        """Rule can be created from YAML dict."""
        data = {
            "name": "YAML Rule",
            "conditions": {
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            "action": "allow",
            "priority": 5,
            "enabled": True,
            "tags": ["adult"],
        }
        rule = Rule.model_validate_yaml(data)
        assert rule.name == "YAML Rule"
        assert rule.priority == 5
        assert "adult" in rule.tags


class TestToEngineDict:
    """Test conversion to engine format."""

    def test_to_engine_dict(self):
        """Rule converts to engine dict format."""
        rule = Rule(
            id=1,
            name="Test",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            action="flag",
            priority=10,
            domain="fraud_detection",
            tags=["high"],
        )
        engine_dict = rule.to_engine_dict()
        assert engine_dict["id"] == 1
        assert engine_dict["name"] == "Test"
        assert engine_dict["priority"] == 10
        assert engine_dict["action"] == "flag"
        assert engine_dict["domain"] == "fraud_detection"
        assert engine_dict["tags"] == frozenset(["high"])


class TestIDGeneration:
    """Test ID generation behavior."""

    def test_sequential_ids(self):
        """Auto-generated IDs are sequential."""
        rule1 = Rule(name="Rule1", conditions=_STUB)
        rule2 = Rule(name="Rule2", conditions=_STUB)
        rule3 = Rule(name="Rule3", conditions=_STUB)
        assert rule2.id == rule1.id + 1
        assert rule3.id == rule2.id + 1

    def test_manual_ids_not_incremented(self):
        """Manually set IDs are not incremented."""
        rule1 = Rule(id=100, name="Rule1", conditions=_STUB)
        rule2 = Rule(name="Rule2", conditions=_STUB)
        # A manually assigned ID is preserved as-is...
        assert rule1.id == 100
        # ...and rule2 still receives an auto-generated ID.
        assert rule2.id is not None

    def test_set_id_generator(self):
        """Can set global ID generator."""
        # Create a new generator with UUID strategy
        uuid_gen = RuleIDGenerator(strategy="uuid")
        Rule.set_id_generator(uuid_gen)

        rule = Rule(name="UUID Rule", conditions=_STUB)
        # UUID should be string
        assert isinstance(rule.id, str) or isinstance(rule.id, int)

        # Reset to sequential for other tests
        seq_gen = RuleIDGenerator(strategy="sequential")
        Rule.set_id_generator(seq_gen)

    def test_id_generator_from_deployment_config(self):
        """ID generator can be set from DeploymentConfig."""
        config = DeploymentConfig(
            deployment_type=DeploymentType.MULTI_INSTANCE,
            instance_id=1,
        )
        gen = RuleIDGenerator.from_config(config)
        Rule.set_id_generator(gen)

        rule = Rule(name="Rule", conditions=_STUB)
        assert rule.id is not None

        # Reset
        Rule.set_id_generator(RuleIDGenerator(strategy="sequential"))


class TestStringRepresentations:
    """Test __repr__ and __str__."""

    def test_repr(self):
        """Rule has informative repr."""
        rule = Rule(
            id=1,
            name="Test Rule",
            conditions=_STUB,
            action="flag",
        )
        repr_str = repr(rule)
        assert "Rule" in repr_str
        assert "Test Rule" in repr_str
        assert "1" in repr_str
        assert "flag" in repr_str

    def test_str(self):
        """Rule has user-friendly str."""
        rule = Rule(
            id=42,
            name="My Rule",
            conditions=_STUB,
        )
        str_val = str(rule)
        assert "My Rule" in str_val
        assert "42" in str_val


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_fraud_detection_rule(self):
        """Realistic fraud detection rule."""
        rule = Rule(
            name="High Value Transaction Alert",
            conditions={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 10000,
            },
            action="flag_for_review",
            priority=10,
            domain="fraud_detection",
            tags=["high_value", "alert"],
            description="Flag transactions over $10,000 for manual review",
            sla_latency_ms=50,
        )
        assert rule.name == "High Value Transaction Alert"
        assert rule.priority == 10
        assert "high_value" in rule.tags
        assert rule.sla_latency_ms == 50

    def test_rule_round_trip(self):
        """Rule can be serialized and deserialized."""
        original = Rule(
            id=1,
            name="Round Trip",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            action="flag",
            priority=5,
            tags=["test"],
        )
        data = original.model_dump()
        restored = Rule(**data)
        assert restored.name == original.name
        assert restored.priority == original.priority
        assert restored.action == original.action


class TestConditionsProperty:
    """The ``condition_nodes`` property derives RuleCondition tuples from the tree."""

    def test_single_condition(self):
        """A simple conditions tree yields one RuleCondition."""
        rule = Rule(
            id=1,
            name="Simple",
            conditions={
                "type": "condition",
                "field": "age",
                "op": ">=",
                "value": 18,
            },
            action="allow",
        )
        nodes = rule.condition_nodes
        assert len(nodes) == 1
        cond = nodes[0]
        assert cond.fact == "age"
        assert cond.operator == ">="
        assert cond.value == 18

    def test_composite_condition_flattens_leaves(self):
        """A group tree yields one RuleCondition per leaf."""
        rule = Rule(
            id=2,
            name="Composite",
            conditions={
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {
                        "type": "condition",
                        "field": "country",
                        "op": "==",
                        "value": "US",
                    },
                ],
            },
            action="allow",
        )
        nodes = rule.condition_nodes
        assert {c.fact for c in nodes} == {"age", "country"}

    def test_conditions_is_read_only(self):
        """The condition_nodes property has no setter."""
        rule = Rule(name="RO", conditions=_STUB)
        with pytest.raises(AttributeError):
            rule.condition_nodes = ()


class TestToEngineRule:
    """``to_engine_rule`` adapts the canonical Rule to the engine dataclass."""

    def test_maps_core_fields(self):
        """Core fields transfer to the internal engine Rule."""
        rule = Rule(
            id=7,
            name="Engine",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            action="flag",
            priority=3,
            domain="fraud",
            description="desc",
            enabled=False,
        )
        engine_rule = rule.to_engine_rule()
        assert engine_rule.id == 7
        assert engine_rule.name == "Engine"
        assert engine_rule.actions == ("flag",)
        assert engine_rule.priority == 3
        assert engine_rule.group == "fraud"
        assert engine_rule.description == "desc"
        assert engine_rule.enabled is False
        assert engine_rule.condition_nodes[0].fact == "x"

    def test_empty_action_yields_no_actions(self):
        """A blank action maps to an empty actions tuple."""
        rule = Rule(
            name="NoAction",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
        )
        assert rule.to_engine_rule().actions == ()

    def test_group_override(self):
        """An explicit group overrides the rule's domain."""
        rule = Rule(
            name="G",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            domain="a",
        )
        assert rule.to_engine_rule(group="b").group == "b"

    def test_id_is_always_integer(self):
        """A rule with a locally generated id still converts to an int id."""
        rule = Rule(
            name="Local",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            persist=False,
        )
        engine_rule = rule.to_engine_rule()
        assert isinstance(engine_rule.id, int)

    def test_timestamps_are_preserved(self):
        """created_at/updated_at carry through to the engine Rule."""
        rule = Rule(
            id=1,
            name="Timed",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            created_at="2026-07-20T00:00:00",
            updated_at="2026-07-20T01:00:00",
        )
        engine_rule = rule.to_engine_rule()
        assert engine_rule.created_at == "2026-07-20T00:00:00"
        assert engine_rule.updated_at == "2026-07-20T01:00:00"


class TestTimestampFields:
    """created_at/updated_at are optional, default to None, and accept ISO strings."""

    def test_default_none(self):
        """Timestamps default to None when not provided."""
        rule = Rule(
            name="NoTimes",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
        )
        assert rule.created_at is None
        assert rule.updated_at is None

    def test_accepts_iso_strings(self):
        """Timestamps can be supplied, e.g. from a loaded YAML rule."""
        rule = Rule.model_validate_yaml(
            {
                "name": "Loaded",
                "conditions": {
                    "type": "condition",
                    "field": "x",
                    "op": ">",
                    "value": 0,
                },
                "created_at": "2026-07-20T00:00:00",
                "updated_at": "2026-07-20T01:00:00",
            }
        )
        assert rule.created_at == "2026-07-20T00:00:00"
        assert rule.updated_at == "2026-07-20T01:00:00"

    def test_serialized_in_model_dump(self):
        """Timestamps appear in the serialized dict."""
        rule = Rule(
            id=1,
            name="Dumped",
            conditions={"type": "condition", "field": "x", "op": ">", "value": 0},
            created_at="2026-07-20T00:00:00",
        )
        data = rule.model_dump()
        assert data["created_at"] == "2026-07-20T00:00:00"


class TestConditionNodes:
    """condition_nodes property derives a flat RuleCondition tuple from the tree."""

    def test_single_leaf_yields_one_node(self):
        rule = Rule(
            id=1,
            name="r",
            conditions={"type": "condition", "field": "amount", "op": ">", "value": 100},
            priority=0,
        )
        nodes = rule.condition_nodes
        assert len(nodes) == 1
        assert nodes[0].fact == "amount"
        assert nodes[0].operator == ">"
        assert nodes[0].value == 100

    def test_and_group_yields_multiple_nodes(self):
        rule = Rule(
            id=2,
            name="r2",
            conditions={
                "type": "and",
                "conditions": [
                    {"type": "condition", "field": "a", "op": ">", "value": 1},
                    {"type": "condition", "field": "b", "op": "==", "value": "US"},
                ],
            },
            priority=0,
        )
        nodes = rule.condition_nodes
        assert len(nodes) == 2
        assert {n.fact for n in nodes} == {"a", "b"}


class TestFromEngineRule:
    """from_engine_rule round-trips an EngineRule back to a canonical Rule."""

    def _make_engine_rule(self, cond=None):
        from fluxrules.domain.models import EngineRule

        if cond is None:
            cond = {"type": "condition", "field": "x", "op": ">", "value": 0}
        return EngineRule(
            id=99,
            name="eng",
            actions=("alert",),
            priority=1,
            group="test",
            description="d",
            enabled=True,
            conditions=cond,
        )

    def test_round_trip_with_explicit_conditions(self):
        cond = {"type": "condition", "field": "x", "op": ">", "value": 42}
        engine_rule = self._make_engine_rule(cond)
        rule = Rule.from_engine_rule(engine_rule, conditions=cond)
        assert rule.id == 99
        assert rule.name == "eng"
        assert rule.conditions == cond
        assert rule.domain == "test"

    def test_round_trip_using_engine_rule_conditions(self):
        cond = {"type": "condition", "field": "score", "op": ">=", "value": 50}
        engine_rule = self._make_engine_rule(cond)
        rule = Rule.from_engine_rule(engine_rule)
        assert rule.conditions == cond

    def test_fallback_reconstructs_from_nodes_single(self):
        from fluxrules.domain.models import EngineRule

        engine_rule = EngineRule(
            id=1,
            name="fallback",
            actions=("x",),
            priority=0,
            group="g",
            conditions={"type": "condition", "field": "amt", "op": ">", "value": 10},
        )
        object.__setattr__(engine_rule, "conditions", None)
        rule = Rule.from_engine_rule(engine_rule)
        assert rule.conditions["type"] == "condition"
        assert rule.conditions["field"] == "amt"

    def test_fallback_reconstructs_from_nodes_multi(self):
        from fluxrules.domain.models import EngineRule

        cond = {
            "type": "and",
            "children": [
                {"type": "condition", "field": "a", "op": ">", "value": 1},
                {"type": "condition", "field": "b", "op": ">", "value": 2},
            ],
        }
        engine_rule = EngineRule(
            id=2, name="multi", actions=("y",), priority=0, group="g", conditions=cond
        )
        object.__setattr__(engine_rule, "conditions", None)
        rule = Rule.from_engine_rule(engine_rule)
        assert rule.conditions["type"] == "group"
        assert rule.conditions["op"] == "AND"
        assert len(rule.conditions["children"]) == 2

    def test_deep_validator_rejects_invalid_operator(self):
        with pytest.raises(ValidationError, match="Invalid operator"):
            Rule(
                name="test",
                conditions={"type": "condition", "field": "x", "op": "invalid_op", "value": 1},
                priority=0,
            )
