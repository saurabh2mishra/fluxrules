"""NOT over missing fields: the less common condition shapes.

The main missing-field tests cover NOT over leaves and simple groups. These
cover the rest of the three-valued walk (OR, exists and unknown nodes under a
NOT), list-form NOT, accumulate nodes on the compiled path, and the engine's
lazy NotState creation.
"""

from __future__ import annotations

import pytest

from fluxrules import F, FieldNotFoundError, Rule
from fluxrules.domain.conditions.missing_fields import (
    NotState,
    evaluate_tristate,
    leaf_fields,
    resolve_not,
)
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.phreak.condition_compiler import compile_condition


def _leaf(field: str, value: object = 1) -> dict:
    return {"type": "condition", "field": field, "op": "==", "value": value}


def _present(node: dict, facts: dict) -> bool:
    return facts[node["field"]] == node["value"]


def _walk(node, facts, other=lambda node, facts: False):
    return evaluate_tristate(node, facts, leaf=_present, other=other, empty=True)


class TestTristateWalk:
    def test_non_dict_node_is_false(self):
        assert _walk("junk", {}) is False

    def test_case_typo_raises(self):
        with pytest.raises(FieldNotFoundError, match="Did you mean 'amount'"):
            _walk(_leaf("Amount"), {"amount": 1})

    def test_or_with_a_true_branch_is_true(self):
        node = {"type": "or", "conditions": [_leaf("missing"), _leaf("x")]}
        assert _walk(node, {"x": 1}) is True

    def test_exists_field(self):
        assert _walk({"type": "exists", "field": "x"}, {"x": 1}) is True
        assert _walk({"type": "exists", "field": "x"}, {"x": None}) is False

    def test_exists_with_a_condition(self):
        node = {"type": "exists", "condition": _leaf("x")}
        assert _walk(node, {"x": 1}) is True
        assert _walk(node, {}) is None

    def test_exists_with_nothing_is_false(self):
        assert _walk({"type": "exists"}, {}) is False

    def test_unknown_nodes_go_to_other(self):
        seen = []
        node = {"type": "accumulate", "field": "x", "function": "sum"}
        assert _walk(node, {}, other=lambda n, f: seen.append(n) or True) is True
        assert seen == [node]

    def test_leaf_fields_skips_non_dict_children(self):
        node = {"type": "and", "conditions": ["junk", _leaf("a")]}
        assert leaf_fields(node) == ("a",)

    def test_leaf_fields_skips_leaves_without_a_field(self):
        assert leaf_fields({"type": "condition", "field": "", "op": "==", "value": 1}) == ()


class TestResolveNot:
    def test_default_mode_returns_plain_once_warned(self):
        state = NotState({"type": "not", "condition": _leaf("blocked", True)})
        state.warned = True
        result = resolve_not(
            state, True, {}, None, leaf=_present, other=lambda n, f: False, empty=True
        )
        assert result is True


# Rules where the NOT fires only because "missing" is absent; under
# missing_field="unknown" none of them may fire.
_UNKNOWN_SHAPES = {
    "or_inside_and": {
        "type": "not",
        "condition": {
            "type": "and",
            "conditions": [_leaf("missing"), {"type": "or", "conditions": [_leaf("x")]}],
        },
    },
    "exists_inside_and": {
        "type": "not",
        "condition": {
            "type": "and",
            "conditions": [_leaf("missing"), {"type": "exists", "field": "x"}],
        },
    },
    "list_form_not": {"type": "not", "conditions": [_leaf("missing")]},
}


def _dict_rule(conditions: dict) -> dict:
    # Dict rules reach the engine without Rule validation, so any shape works.
    return {"id": 1, "name": "r", "action": "flag", "conditions": conditions}


class TestEngineShapes:
    @pytest.mark.parametrize("compile_conditions", [False, True])
    @pytest.mark.parametrize("shape", sorted(_UNKNOWN_SHAPES))
    def test_not_does_not_fire_on_missing_field(self, shape, compile_conditions):
        engine = PhreakEngine(
            config=EngineConfig(missing_field="unknown"), compile_conditions=compile_conditions
        )
        engine.load_rules([_dict_rule(_UNKNOWN_SHAPES[shape])])
        assert engine.evaluate({"x": 1}).fired_rules == []

    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_empty_list_form_not_is_true(self, compile_conditions):
        # Paired with a real field: a rule with no fields is never a candidate.
        engine = PhreakEngine(compile_conditions=compile_conditions)
        engine.load_rules(
            [
                _dict_rule(
                    {"type": "and", "conditions": [_leaf("x"), {"type": "not", "conditions": []}]}
                )
            ]
        )
        assert engine.evaluate({"x": 1}).fired_rules == [1]

    def test_accumulate_under_not_uses_the_interpreter_fallback(self):
        node = {
            "type": "not",
            "condition": {
                "type": "and",
                "conditions": [
                    _leaf("missing"),
                    {"type": "accumulate", "field": "x", "function": "sum"},
                ],
            },
        }
        for compile_conditions in (False, True):
            engine = PhreakEngine(
                config=EngineConfig(missing_field="unknown"),
                compile_conditions=compile_conditions,
            )
            engine.load_rules([_dict_rule(node)])
            for _ in range(2):  # the second call reuses the compiled fallback
                assert engine.evaluate({"x": 1}).fired_rules == []

    def test_compiled_accumulate_without_a_fallback_is_false(self):
        node = {
            "type": "not",
            "condition": {
                "type": "and",
                "conditions": [
                    _leaf("missing"),
                    {"type": "accumulate", "field": "x", "function": "sum"},
                ],
            },
        }
        compiled = compile_condition(node, EngineConfig(missing_field="unknown"))
        # The accumulate node counts as False, so the AND is False and the NOT
        # is definitely True: missing data cannot change it.
        assert compiled({"x": 1}) is True

    def test_not_state_is_created_when_missing(self):
        engine = PhreakEngine(config=EngineConfig(missing_field="unknown"))
        engine.load_rules([Rule(id=1, name="r", conditions=~(F("blocked") == True), action="x")])  # noqa: E712
        engine._not_states.clear()
        assert engine.evaluate({"amount": 1}).fired_rules == []
        assert len(engine._not_states) == 1
