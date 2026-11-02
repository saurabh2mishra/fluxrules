"""FieldNotFoundError - missing fact field raises instead of silently returning False."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from fluxrules import F, FieldNotFoundError, MissingFieldNotWarning, Rule, evaluate
from fluxrules.domain.errors import canonical_field_name, is_field_typo
from fluxrules.engine.phreak import PhreakEngine


def _rule(conditions, action="flag"):
    return Rule(name="test", conditions=conditions, action=action)


# ---------------------------------------------------------------------------
# Error class itself
# ---------------------------------------------------------------------------


class TestFieldNotFoundError:
    def test_message_contains_field_name(self):
        err = FieldNotFoundError.for_field("Amount", {"amount": 1, "country": "US"})
        assert "Amount" in str(err)

    def test_message_lists_available_keys(self):
        err = FieldNotFoundError.for_field("Amount", {"amount": 1, "country": "US"})
        assert "amount" in str(err)
        assert "country" in str(err)

    def test_did_you_mean_suggestion_for_case_typo(self):
        err = FieldNotFoundError.for_field("Amount", {"amount": 1})
        assert "amount" in str(err)
        assert "Did you mean" in str(err)

    def test_no_suggestion_for_unrelated_name(self):
        err = FieldNotFoundError.for_field("xyz123", {"amount": 1, "country": "US"})
        assert "Did you mean" not in str(err)

    def test_is_fluxrules_error(self):
        from fluxrules import FluxRulesError

        assert issubclass(FieldNotFoundError, FluxRulesError)

    def test_stable_code(self):
        assert FieldNotFoundError.code == "FIELD_NOT_FOUND"


# ---------------------------------------------------------------------------
# evaluate() raises for missing field (reference evaluator path)
# ---------------------------------------------------------------------------


class TestEvaluateRaisesOnMissingField:
    def test_wrong_case_raises(self):
        rule = _rule(F("Amount") > 10000)
        with pytest.raises(FieldNotFoundError, match="Amount"):
            evaluate(rule, {"amount": 50000})

    def test_all_caps_raises(self):
        rule = _rule(F("AMOUNT") > 10000)
        with pytest.raises(FieldNotFoundError, match="AMOUNT"):
            evaluate(rule, {"amount": 50000})

    def test_completely_absent_unrelated_field_does_not_raise(self):
        # "score" has no resemblance to "amount" - different fact schema, not a typo
        rule = _rule(F("score") > 50)
        result = evaluate(rule, {"amount": 100})
        assert result.fired_rules == []

    def test_correct_field_does_not_raise(self):
        rule = _rule(F("amount") > 10000)
        result = evaluate(rule, {"amount": 50000})
        assert rule.id in result.fired_rules

    def test_error_lists_available_keys(self):
        rule = _rule(F("Amount") > 10000)
        with pytest.raises(FieldNotFoundError) as exc_info:
            evaluate(rule, {"amount": 50000, "country": "US"})
        msg = str(exc_info.value)
        assert "amount" in msg
        assert "country" in msg

    def test_did_you_mean_in_error(self):
        rule = _rule(F("Amount") > 10000)
        with pytest.raises(FieldNotFoundError, match="Did you mean 'amount'"):
            evaluate(rule, {"amount": 50000})

    def test_and_group_raises_on_first_missing_field(self):
        rule = _rule((F("Amount") > 10000) & (F("country") == "US"))
        with pytest.raises(FieldNotFoundError, match="Amount"):
            evaluate(rule, {"amount": 50000, "country": "US"})

    def test_or_group_raises_when_branch_field_missing(self):
        rule = _rule((F("Amount") > 10000) | (F("country") == "US"))
        with pytest.raises(FieldNotFoundError):
            evaluate(rule, {"amount": 50000, "country": "US"})

    def test_not_does_not_raise_for_unrelated_absent_field(self):
        # "blocked" has no resemblance to "name" - absent field returns False,
        # so ~False = True and the rule fires without an error. Under the
        # default missing_field=None it also warns that 2.0 will not fire it
        # (see test_missing_field_semantics.py).
        rule = _rule(~(F("blocked") == True))  # noqa: E712
        with pytest.warns(MissingFieldNotWarning):
            result = evaluate(rule, {"name": "Alice"})
        assert rule.id in result.fired_rules


# ---------------------------------------------------------------------------
# exists() does NOT raise for absent fields - that is its purpose
# ---------------------------------------------------------------------------


class TestExistsDoesNotRaise:
    def test_exists_returns_false_when_absent(self):
        rule = _rule(F("email").exists())
        result = evaluate(rule, {"name": "Alice"})
        assert result.fired_rules == []

    def test_exists_returns_true_when_present(self):
        rule = _rule(F("email").exists())
        result = evaluate(rule, {"email": "a@b.com"})
        assert rule.id in result.fired_rules


# ---------------------------------------------------------------------------
# PhreakEngine raises too (both compiled closure and interpreter)
# ---------------------------------------------------------------------------


class TestPhreakEngineRaises:
    def _engine_with(self, rule):
        engine = PhreakEngine()
        engine.load_rules([rule])
        return engine

    def test_phreak_raises_on_missing_field(self):
        rule = _rule(F("Amount") > 10000)
        engine = self._engine_with(rule)
        with pytest.raises(FieldNotFoundError, match="Amount"):
            engine.evaluate({"amount": 50000})

    def test_phreak_correct_field_fires(self):
        rule = _rule(F("amount") > 10000)
        engine = self._engine_with(rule)
        result = engine.evaluate({"amount": 50000})
        assert rule.id in result.fired_rules

    def test_phreak_did_you_mean_hint(self):
        rule = _rule(F("Amount") > 10000)
        engine = self._engine_with(rule)
        with pytest.raises(FieldNotFoundError, match="Did you mean 'amount'"):
            engine.evaluate({"amount": 50000})

    def test_phreak_exists_does_not_raise(self):
        rule = _rule(F("email").exists())
        engine = self._engine_with(rule)
        result = engine.evaluate({"name": "Alice"})
        assert result.fired_rules == []

    def test_phreak_or_typo_raises_regardless_of_branch_order(self):
        # Typo detection is a single per-fact scan, so it does not depend on OR
        # short-circuit order: both arrangements raise for the same fact.
        fact = {"amount": 50000, "country": "US"}
        typo_first = self._engine_with(_rule((F("Amount") > 10000) | (F("country") == "US")))
        with pytest.raises(FieldNotFoundError, match="Amount"):
            typo_first.evaluate(fact)
        typo_second = self._engine_with(_rule((F("country") == "US") | (F("Amount") > 10000)))
        with pytest.raises(FieldNotFoundError, match="Amount"):
            typo_second.evaluate(fact)

    def test_phreak_not_typo_raises(self):
        rule = _rule(~(F("Blocked") == True))  # noqa: E712
        engine = self._engine_with(rule)
        with pytest.raises(FieldNotFoundError, match="Blocked"):
            engine.evaluate({"blocked": False})

    def test_phreak_clean_or_does_not_raise(self):
        rule = _rule((F("amount") > 5000) | (F("country") == "US"))
        engine = self._engine_with(rule)
        result = engine.evaluate({"amount": 10, "country": "US"})
        assert rule.id in result.fired_rules


# ---------------------------------------------------------------------------
# Key-style variants: only with a fact schema; case variants always
# ---------------------------------------------------------------------------


_KEY_STYLES = ["user_age", "userAge", "UserAge", "user-age", "userage", "USER_AGE"]


class _Person(BaseModel):
    user_age: int


class TestKeyStyleVariants:
    @pytest.mark.parametrize("key", _KEY_STYLES)
    def test_canonical_form_is_shared_with_styles(self, key):
        assert canonical_field_name(key, styles=True) == "userage"

    def test_canonical_form_without_styles_only_lowercases(self):
        assert canonical_field_name("User_Age", styles=False) == "user_age"

    def test_dot_is_significant(self):
        assert canonical_field_name("user.name") != canonical_field_name("username")
        assert not is_field_typo("user.name", {"username": "x"}, styles=True)

    @pytest.mark.parametrize("rule_field", _KEY_STYLES)
    @pytest.mark.parametrize("fact_key", _KEY_STYLES)
    def test_is_field_typo_matches_every_style_when_asked(self, rule_field, fact_key):
        if rule_field == fact_key:
            pytest.skip("exact match is not a typo")
        assert is_field_typo(rule_field, {fact_key: 30}, styles=True)

    def test_is_field_typo_matches_case_only_by_default(self):
        assert is_field_typo("userAge", {"userage": 30})
        assert not is_field_typo("userAge", {"user_age": 30})

    @pytest.mark.parametrize(
        ("rule_field", "fact_key"),
        [("field_0", "field_10"), ("line_1", "line_2"), ("score", "amount"), ("a_b", "a_c")],
    )
    def test_different_fields_are_not_typos(self, rule_field, fact_key):
        assert not is_field_typo(rule_field, {fact_key: 1}, styles=True)

    @pytest.mark.parametrize("compile_conditions", [False, True])
    @pytest.mark.parametrize("fact_key", ["userAge", "user-age", "UserAge"])
    def test_phreak_with_schema_raises_for_style_variant(self, compile_conditions, fact_key):
        engine = PhreakEngine(compile_conditions=compile_conditions, fact_schema=_Person)
        engine.load_rules([_rule(F("user_age") >= 18)])
        with pytest.raises(FieldNotFoundError, match=f"Did you mean '{fact_key}'"):
            engine.evaluate({fact_key: 30})

    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_phreak_without_schema_allows_style_variants(self, compile_conditions):
        # One ruleset serving two fact shapes that spell the id differently.
        engine = PhreakEngine(compile_conditions=compile_conditions)
        engine.load_rules(
            [
                Rule(id=1, name="a", conditions=F("user_id") > 0, action="x"),
                Rule(id=2, name="b", conditions=F("userId") > 0, action="y"),
            ]
        )
        assert engine.evaluate({"user_id": 1}).fired_rules == [1]
        assert engine.evaluate({"userId": 1}).fired_rules == [2]

    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_phreak_without_schema_still_raises_for_case_variant(self, compile_conditions):
        engine = PhreakEngine(compile_conditions=compile_conditions)
        engine.load_rules([_rule(F("userAge") >= 18)])
        with pytest.raises(FieldNotFoundError, match="Did you mean 'USERAGE'"):
            engine.evaluate({"USERAGE": 30})

    def test_evaluate_without_schema_allows_style_variant(self):
        assert evaluate(_rule(F("userAge") >= 18), {"user_age": 30}).fired_rules == []

    def test_dotted_rule_with_unrelated_flat_key_is_silent(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("user.name") == "x")])
        assert engine.evaluate({"username": "x"}).fired_rules == []

    def test_numbered_family_still_silent_on_engine(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("field_0") == 1)])
        assert engine.evaluate({"field_10": 1}).fired_rules == []

    def test_hint_prefers_same_shape_key_over_close_spelling(self):
        err = FieldNotFoundError.for_field("userAge", {"user_age": 1, "userAgent": "x"})
        assert "Did you mean 'user_age'" in str(err)


class TestUnflattenedNestedFacts:
    def test_dotted_rule_against_nested_dict_raises_with_flatten_hint(self):
        with pytest.raises(FieldNotFoundError, match="flatten"):
            evaluate(_rule(F("user.age") >= 18), {"user": {"age": 30}})

    def test_engine_dotted_rule_against_nested_dict_raises(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("user.age") >= 18)])
        with pytest.raises(FieldNotFoundError, match="'user' holds a nested value"):
            engine.evaluate({"user": {"age": 30}})

    def test_dotted_rule_with_scalar_parent_is_silent(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("user.age") >= 18)])
        assert engine.evaluate({"user": "alice"}).fired_rules == []


class TestExistsField:
    def test_exists_field_itself_never_raises(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("Amount").exists())])
        assert engine.evaluate({"amount": 5}).fired_rules == []


class TestNotStateIsBuiltOnce:
    def test_domain_evaluator_reuses_not_state(self):
        from fluxrules.domain.conditions import evaluator

        rule = _rule(~(F("blocked") == True))  # noqa: E712
        node = rule.conditions
        first = evaluator._not_state(node)
        evaluate(rule, {"amount": 1})
        assert evaluator._not_state(node) is first

    def test_compiled_not_compiles_each_leaf_once(self, monkeypatch):
        from fluxrules.engine.configuration import EngineConfig
        from fluxrules.engine.phreak import condition_compiler

        engine = PhreakEngine(config=EngineConfig(missing_field="unknown"), compile_conditions=True)
        engine.load_rules([_rule(~((F("a") == 1) & (F("b") == 2)))])
        calls = []
        real = condition_compiler._compile_leaf
        monkeypatch.setattr(
            condition_compiler,
            "_compile_leaf",
            lambda node, flags: calls.append(node.get("field")) or real(node, flags),
        )
        for _ in range(5):
            engine.evaluate({"a": 2})  # "b" missing: the NOT takes the slow path
        assert sorted(calls) == ["a"]


class TestSecondReviewEngine:
    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_typo_inside_exists_condition_raises(self, compile_conditions):
        engine = PhreakEngine(compile_conditions=compile_conditions)
        # A dict rule reaches the engine without Rule validation.
        engine.load_rules(
            [
                {
                    "id": 1,
                    "name": "t",
                    "action": "x",
                    "conditions": {
                        "type": "exists",
                        "condition": {
                            "type": "condition",
                            "field": "Amount",
                            "op": ">",
                            "value": 5,
                        },
                    },
                }
            ]
        )
        with pytest.raises(FieldNotFoundError, match="Did you mean 'amount'"):
            engine.evaluate({"amount": 10})

    def test_not_state_is_kept_when_mode_changes_after_load(self):
        from fluxrules.engine.configuration import EngineConfig

        config = EngineConfig(missing_field="false")
        engine = PhreakEngine(config=config)
        engine.load_rules([_rule(~(F("blocked") == True))])  # noqa: E712
        states_before = dict(engine._not_states)
        assert states_before  # built at load whatever the mode
        config.missing_field = "unknown"
        for _ in range(3):
            assert engine.evaluate({"amount": 1}).fired_rules == []
        assert engine._not_states == states_before

    def test_domain_not_cache_rebuilds_when_child_is_replaced(self):
        from fluxrules.domain.conditions import evaluator

        node = {
            "type": "not",
            "condition": {"type": "condition", "field": "a", "op": "==", "value": 1},
        }
        first = evaluator._not_state(node)
        node["condition"] = {"type": "condition", "field": "b", "op": "==", "value": 1}
        second = evaluator._not_state(node)
        assert second is not first
        assert second.fields == ("b",)

    def test_domain_not_cache_is_bounded(self, monkeypatch):
        from fluxrules.domain.conditions import evaluator

        monkeypatch.setattr(evaluator, "_NOT_STATES_MAX", 3)
        nodes = [
            {
                "type": "not",
                "condition": {"type": "condition", "field": f"f{i}", "op": "==", "value": 1},
            }
            for i in range(5)
        ]
        for node in nodes:
            evaluator._not_state(node)
        assert len(evaluator._NOT_STATES) <= 3
        assert evaluator._NOT_STATES.get(id(nodes[-1]))[0] is nodes[-1]
