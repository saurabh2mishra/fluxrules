"""Operators that make common comparisons easy, and the checks around them.

- ``approx`` compares numbers with ``math.isclose``.
- The ``_ignore_case`` operators compare text with ``str.casefold()``.
- With a fact schema, numeric text on a ``Decimal`` field loads as a
  ``Decimal``, and ``validate_facts="normalize"`` converts dates and numeric
  text in facts.
- The leaf memo tells apart rule values Python calls equal (``True`` and ``1``).
"""

from __future__ import annotations

import datetime as dt
import math
import re
import warnings
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from fluxrules import (
    F,
    MembershipValueWarning,
    Rule,
    RuleValueError,
    RuleValueWarning,
    validate,
)
from fluxrules.domain.conditions.rule_values import reset_value_warnings
from fluxrules.domain.errors import ConditionValidationError
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.operators import compare_operator
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.uncomparable import Uncomparable, reset_warnings


@pytest.fixture(autouse=True)
def fresh_warnings():
    reset_warnings()
    reset_value_warnings()
    yield
    reset_warnings()
    reset_value_warnings()


def _cmp(op, left, right, **flags):
    return compare_operator(
        op,
        left,
        right,
        field_present=True,
        strict_null_handling=flags.get("strict_null_handling", False),
        strict_type_comparison=flags.get("strict_type_comparison", False),
        boolean_string_coercion=flags.get("boolean_string_coercion", False),
        field="v",
    )


def _reason(outcome):
    assert outcome.__class__ is Uncomparable, outcome
    return outcome.issue.reason


def _rule(condition, rid=1, name="r"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Rule(id=rid, name=name, conditions=condition, action="a")


def _fires(condition, fact, **engine):
    e = PhreakEngine(**engine)
    e.load_rules([_rule(condition)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return e.evaluate(fact).fired_rules == [1]


class TestApprox:
    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (0.1 + 0.2, 0.3, True),
            (0.3001, 0.3, False),
            (0.305, {"value": 0.3, "abs_tol": 0.01}, True),
            (0.32, {"value": 0.3, "abs_tol": 0.01}, False),
            (101.0, {"value": 100, "rel_tol": 0.02}, True),
            (103.0, {"value": 100, "rel_tol": 0.02}, False),
            (5, 5, True),
            (Decimal("0.3"), 0.3, True),
            (Decimal("0.30"), Decimal("0.3"), True),
            (1e-12, 0, False),
            (1e-12, {"value": 0, "abs_tol": 1e-9}, True),
            (math.inf, math.inf, True),
        ],
    )
    def test_closeness(self, left, right, expected):
        assert _cmp("approx", left, right) is expected

    @pytest.mark.parametrize(
        ("left", "right", "reason"),
        [
            ("abc", 0.3, "approx compares numbers only"),
            ("0.3", 0.3, "approx compares numbers only"),
            (None, 0.3, "approx compares numbers only"),
            (True, 1, "approx compares numbers only"),
            (0.3, "0.3", "approx compares numbers only"),
            (math.nan, 0.3, "NaN is not close to any number"),
            (0.3, {"value": math.nan}, "NaN is not close to any number"),
        ],
    )
    def test_values_that_are_not_numbers_cannot_be_compared(self, left, right, reason):
        assert _reason(_cmp("approx", left, right)) == reason

    def test_the_issue_names_the_target_type(self):
        issue = _cmp("approx", "x", {"value": Decimal("1"), "abs_tol": 0.1}).issue
        assert (issue.fact_type, issue.rule_type) == ("str", "Decimal")

    def test_f_writes_the_tolerances_into_the_value(self):
        assert F("t").approx(0.3).to_dict()["value"] == 0.3
        assert F("t").approx(0.3, abs_tol=0.01).to_dict()["value"] == {
            "value": 0.3,
            "abs_tol": 0.01,
        }
        assert F("t").approx(0.3, rel_tol=1e-6, abs_tol=0).to_dict()["value"] == {
            "value": 0.3,
            "abs_tol": 0,
            "rel_tol": 1e-6,
        }

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            ({"value": 0.3, "tol": 1}, "Unknown keys ['tol'] in the 'approx' value"),
            ({"abs_tol": 1}, "is missing its 'value'"),
            ({"value": 0.3, "abs_tol": -1}, "'abs_tol' in the 'approx' value"),
            ({"value": 0.3, "rel_tol": True}, "'rel_tol' in the 'approx' value"),
            ({"value": 0.3, "rel_tol": "1"}, "must be a number of 0 or more"),
        ],
    )
    def test_a_malformed_value_is_refused(self, value, message):
        with pytest.raises(ValueError, match=re.escape(message)):
            Rule(
                id=1,
                name="r",
                conditions={"type": "condition", "field": "t", "op": "approx", "value": value},
                action="a",
            )
        with pytest.raises(ConditionValidationError):
            from fluxrules.domain.conditions.validation import validate_conditions

            validate_conditions({"type": "condition", "field": "t", "op": "approx", "value": value})

    @pytest.mark.parametrize("target", ["0.3", None, True, [1]])
    def test_a_target_that_is_not_a_number_warns(self, target):
        with pytest.warns(RuleValueWarning, match="'approx' needs a number"):
            Rule(id=1, name="r", conditions=F("t").approx(target), action="a")

    def test_every_engine_mode_answers_alike(self):
        condition = F("t").approx(0.3, abs_tol=0.01)
        for engine in ({}, {"compile_conditions": True}, {"alpha_prefilter": False}):
            assert _fires(condition, {"t": 0.1 + 0.2}, **engine)
            assert not _fires(condition, {"t": 0.4}, **engine)

    def test_strict_types_accept_two_numbers(self):
        config = EngineConfig(strict_type_comparison=True)
        assert _fires(F("t").approx(5), {"t": 5.0}, config=config)

    def test_a_yaml_rule_file(self, tmp_path: Path):
        from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml

        path = tmp_path / "rules.yaml"
        path.write_text(
            "- id: 1\n  name: r\n  action: a\n"
            "  conditions: {type: condition, field: t, op: approx, "
            "value: {value: 0.3, abs_tol: 0.01}}\n"
        )
        engine = PhreakEngine()
        engine.load_rules(load_rules_from_yaml(str(path)))
        assert engine.evaluate({"t": 0.305}).fired_rules == [1]


class TestIgnoreCase:
    @pytest.mark.parametrize(
        ("op", "left", "right", "expected"),
        [
            ("equals_ignore_case", "STRASSE", "straße", True),
            ("equals_ignore_case", "Oslo", "OSLO", True),
            ("equals_ignore_case", "Oslo", "Bergen", False),
            ("equals_ignore_case", 5, "5", False),
            ("equals_ignore_case", "5", 5, False),
            ("in_ignore_case", "no", ["NO", "SE"], True),
            ("in_ignore_case", "dk", ["NO", "SE"], False),
            ("in_ignore_case", "5", [5, "x"], False),
            ("in_ignore_case", 5, ["5"], False),
            ("contains_ignore_case", "Hello World", "WORLD", True),
            ("contains_ignore_case", "Hello", "xyz", False),
            ("contains_ignore_case", ["VIP", "new"], "vip", True),
            ("contains_ignore_case", ["VIP"], "vi", False),
            ("contains_ignore_case", [5], "5", False),
            ("starts_with_ignore_case", "Hello", "HE", True),
            ("starts_with_ignore_case", "Hello", "lo", False),
            ("ends_with_ignore_case", "Hello", "LO", True),
            ("ends_with_ignore_case", "Hello", "he", False),
        ],
    )
    def test_answers(self, op, left, right, expected):
        assert _cmp(op, left, right) is expected

    @pytest.mark.parametrize(
        ("op", "left", "right"),
        [
            ("contains_ignore_case", 5, "5"),
            ("contains_ignore_case", "abc", 5),
            ("starts_with_ignore_case", 75, "7"),
            ("ends_with_ignore_case", True, "e"),
            ("starts_with_ignore_case", "abc", None),
        ],
    )
    def test_looking_inside_a_value_that_is_not_text_cannot_be_done(self, op, left, right):
        assert _reason(_cmp(op, left, right)) == "the _ignore_case operators compare text only"

    def test_none_is_no_match_and_not_reported(self):
        for op in ("equals_ignore_case", "contains_ignore_case", "starts_with_ignore_case"):
            assert _cmp(op, None, "a") is False

    def test_a_single_in_value_becomes_a_list(self):
        with pytest.warns(MembershipValueWarning, match="equals_ignore_case"):
            condition = F("c").in_ignore_case("NO")
        assert condition.to_dict()["value"] == ["NO"]

    @pytest.mark.parametrize(
        "condition",
        [
            F("c").equals_ignore_case(5),
            F("c").contains_ignore_case(None),
            F("c").starts_with_ignore_case(7),
            F("c").ends_with_ignore_case(["x"]),
        ],
    )
    def test_a_rule_value_that_is_not_text_warns(self, condition):
        with pytest.warns(RuleValueWarning, match="needs text"):
            Rule(id=1, name="r", conditions=condition, action="a")

    def test_an_in_value_that_is_not_text_warns(self):
        with pytest.warns(RuleValueWarning, match="'in_ignore_case' compares text"):
            Rule(id=1, name="r", conditions=F("c").in_ignore_case(["NO", 5]), action="a")

    def test_every_engine_mode_answers_alike(self):
        condition = F("city").equals_ignore_case("oslo") & F("tags").contains_ignore_case("vip")
        fact = {"city": "OSLO", "tags": ["VIP"]}
        for engine in ({}, {"compile_conditions": True}, {"alpha_prefilter": False}):
            assert _fires(condition, fact, **engine)
            assert not _fires(condition, {"city": "Bergen", "tags": ["VIP"]}, **engine)


class Payment(BaseModel):
    amount: float
    total: Decimal
    country: str
    placed: dt.date


class TestSchema:
    def _load(self, condition):
        engine = PhreakEngine(fact_schema=Payment)
        engine.load_rules([_rule(condition, name="r")])
        return engine

    @pytest.mark.parametrize(
        ("condition", "message"),
        [
            (F("amount").equals_ignore_case("x"), "'equals_ignore_case' tests text"),
            (F("placed").starts_with_ignore_case("2024"), "'starts_with_ignore_case' tests text"),
            (F("country").approx(5), "'approx' compares numbers"),
            (F("total") == 10.1, 'Write "10.1" in quotes, which loads as an exact Decimal.'),
            (F("total").isin([10.1]), 'Write "10.1" in quotes'),
        ],
    )
    def test_refuses(self, condition, message):
        with pytest.raises(RuleValueError, match=message):
            self._load(condition)

    @pytest.mark.parametrize(
        "condition",
        [
            F("amount").approx(5.5),
            F("total").approx(10.1),
            F("total") > 10.1,
            F("country").equals_ignore_case("no"),
            F("country").in_ignore_case(["no", "se"]),
        ],
    )
    def test_loads(self, condition):
        self._load(condition)

    def test_numeric_text_on_a_decimal_field_loads_as_a_decimal(self):
        engine = self._load(F("total") == "10.10")
        (rule,) = engine.rule_repository.rules.values()
        assert rule.conditions["value"] == Decimal("10.10")
        assert isinstance(rule.conditions["value"], Decimal)
        fact = {"amount": 1.0, "total": Decimal("10.1"), "country": "NO", "placed": dt.date.today()}
        assert engine.evaluate(fact).fired_rules == [1]

    def test_validate_lists_the_new_operators(self):
        issues = validate([_rule(F("amount").equals_ignore_case("x"))], fact_schema=Payment)
        assert any("'equals_ignore_case' tests text" in i for i in issues)


class TestNormalizedFacts:
    """With ``validate_facts="normalize"``, dates and numeric text are converted."""

    def test_dates_and_numbers_arrive_typed(self):
        engine = PhreakEngine(fact_schema=Payment, validate_facts="normalize")
        engine.load_rules(
            [
                _rule(F("amount") > 100, 1, "big"),
                _rule(F("placed") >= "2024-05-01", 2, "may"),
                _rule(F("total").approx(Decimal("10.10")), 3, "total"),
            ]
        )
        fact = {"amount": "100.3", "total": "10.10", "country": "NO", "placed": "2024-05-02"}
        result = engine.evaluate(fact)
        assert sorted(result.fired_rules) == [1, 2, 3]
        assert result.comparison_issues == []

    def test_without_a_schema_text_stays_text(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("amount") > 100)])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = engine.evaluate({"amount": "100.3"})
        assert result.fired_rules == []
        assert [i.reason for i in result.comparison_issues] == ["these types cannot be ordered"]


class TestLeafMemoTellsEqualValuesApart:
    """``True == 1`` and ``5.5 == Decimal("5.5")`` in Python, with one hash."""

    @pytest.mark.parametrize("engine", [{}, {"compile_conditions": True}])
    def test_strict_types_do_not_borrow_an_answer(self, engine):
        e = PhreakEngine(config=EngineConfig(strict_type_comparison=True), **engine)
        e.load_rules(
            [
                _rule(F("v") > True, 1, "bool"),
                _rule(F("v") > 1, 2, "int"),
                _rule(F("v") >= 1.0, 3, "float"),
            ]
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert sorted(e.evaluate({"v": 5}).fired_rules) == [2, 3]

    def test_each_rule_value_type_is_reported(self):
        e = PhreakEngine()
        e.load_rules(
            [_rule(F("v").approx(5.5), 1, "f"), _rule(F("v").approx(Decimal("5.5")), 2, "d")]
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = e.evaluate({"v": "x"})
        assert {i.rule_type for i in result.comparison_issues} == {"float", "Decimal"}
