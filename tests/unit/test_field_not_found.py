"""FieldNotFoundError - missing fact field raises instead of silently returning False."""

from __future__ import annotations

import pytest

from fluxrules import F, FieldNotFoundError, Rule, evaluate
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
        # so ~False = True and the rule fires without an error
        rule = _rule(~(F("blocked") == True))  # noqa: E712
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
