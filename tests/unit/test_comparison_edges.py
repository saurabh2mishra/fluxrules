"""Edge cases of the 1.2.0 comparison work: rarely written values and shapes.

Each test pins one path the main test files do not reach: malformed trees,
values of the wrong kind for date fields, nested conversions, cross-fact
quantifiers that bind the same fact or an unbound variable, and the leaf memo
for a mapping value it cannot sort.
"""

from __future__ import annotations

import datetime as dt
import io
import warnings
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel

from fluxrules import F, Rule, RuleValueError
from fluxrules.adapters.loaders.yaml_reading import load_yaml
from fluxrules.domain.comparison_issues import ComparisonIssue
from fluxrules.domain.conditions.rule_values import reset_value_warnings, value_problems
from fluxrules.domain.conditions.schema_values import check_tree
from fluxrules.domain.errors import ComparisonWarning, UncomparableValuesError
from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.operators import compare_operator
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.uncomparable import report, reset_warnings


@pytest.fixture(autouse=True)
def clean_state():
    old = get_config()
    reset_warnings()
    reset_value_warnings()
    yield
    set_config(old)
    reset_warnings()
    reset_value_warnings()


def _rule(condition: Any, rid: int = 1) -> Rule:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Rule(id=rid, name=f"r{rid}", conditions=condition, action="a")


class Event(BaseModel):
    placed: dt.date
    at: dt.datetime
    country: str


FIELDS = {"placed": dt.date, "at": dt.datetime, "country": str}


def _check(tree: Any) -> tuple[Any, list[str]]:
    converted, errors = check_tree(tree, FIELDS, schema_name="Event", rule="r")
    return converted, [e.summary for e in errors]


class TestSchemaValueEdges:
    @pytest.mark.parametrize(
        ("condition", "message"),
        [
            (F("country") == True, "compares it with the boolean True. Write text."),  # noqa: E712
            (F("placed") == 5, "Write an ISO date such as 2024-05-01."),
            (F("placed") >= "2024-13-01", "Write an ISO date such as 2024-05-01."),
            (F("at") > 5, "Write an ISO date and time such as 2024-05-01T09:30:00."),
            (F("at") > "nope, not a date", "Write an ISO date and time"),
            (F("at") > "2024-05-01T99:00", "Write an ISO date and time"),
        ],
    )
    def test_refuses(self, condition, message):
        with pytest.raises(RuleValueError, match=message):
            PhreakEngine(fact_schema=Event).load_rules([_rule(condition)])

    def test_a_date_under_not_is_converted(self):
        tree = (~(F("placed") >= "2024-05-01")).to_dict()
        converted, errors = _check(tree)
        assert errors == []
        assert converted["condition"]["value"] == dt.date(2024, 5, 1)
        assert tree["condition"]["value"] == "2024-05-01"  # the input is not changed

    def test_two_converted_children_of_one_node(self):
        # A node with two condition keys (as a custom node type may have).
        tree = {
            "type": "pair",
            "first": (F("placed") >= "2024-05-01").to_dict(),
            "second": (F("at") < "2024-06-01T00:00:00").to_dict(),
        }
        converted, errors = _check(tree)
        assert errors == []
        assert converted["first"]["value"] == dt.date(2024, 5, 1)
        assert converted["second"]["value"] == dt.datetime(2024, 6, 1)

    def test_a_tree_without_changes_comes_back_as_is(self):
        tree = ((F("country") == "NO") & ~(F("placed") >= dt.date(2024, 5, 1))).to_dict()
        assert _check(tree)[0] is tree

    @pytest.mark.parametrize(
        "tree",
        [
            "not a node",
            ["not a node"],
            {"type": "condition", "field": "placed", "op": "=="},
            {"type": "condition", "field": 5, "op": "==", "value": 1},
            {"type": "condition", "field": "placed", "op": "in", "value": "2024-05-01"},
            {"type": "condition", "field": "placed", "op": "exists_like", "value": 1},
        ],
    )
    def test_shapes_it_does_not_check_pass_through(self, tree):
        assert _check(tree) == (tree, [])


class TestRuleValueEdges:
    def test_approx_against_nan(self):
        assert value_problems(F("t").approx(float("nan")).to_dict()) == [
            "Condition on field 't': 'approx' cannot match NaN. The condition can never match."
        ]

    @pytest.mark.parametrize(
        "tree",
        [
            None,
            "text",
            {"type": "condition", "field": "v", "op": ">"},
            {"type": "condition", "field": "v", "op": 5, "value": None},
        ],
    )
    def test_shapes_it_does_not_check(self, tree):
        assert value_problems(tree) == []


class TestOperatorEdges:
    def test_an_unknown_operator_is_no_match(self):
        assert (
            compare_operator(
                "not_an_operator",
                1,
                1,
                field_present=True,
                strict_null_handling=False,
                strict_type_comparison=False,
                boolean_string_coercion=False,
            )
            is False
        )

    def test_approx_with_only_a_relative_tolerance(self):
        assert F("t").approx(100, rel_tol=0.1).to_dict()["value"] == {"value": 100, "rel_tol": 0.1}

    def test_report_outside_an_evaluation_reads_the_process_config(self):
        issue = ComparisonIssue("v", ">", "str", "int", "these types cannot be ordered")
        set_config(EngineConfig(uncomparable="false"))
        with warnings.catch_warnings():
            warnings.simplefilter("error", ComparisonWarning)
            report(issue)  # neither warns nor raises
        set_config(EngineConfig(uncomparable="raise"))
        with pytest.raises(UncomparableValuesError):
            report(issue)


class TestLeafMemoEdges:
    def test_a_mapping_value_it_cannot_sort_is_compared_directly(self):
        value = {"a": 1, 2: "b"}  # keys of two types cannot be sorted
        for engine in ({}, {"compile_conditions": True}):
            e = PhreakEngine(**engine)
            e.load_rules([_rule(F("v") == value)])
            assert e.evaluate({"v": {"a": 1, 2: "b"}}).fired_rules == [1]


class TestYamlEdges:
    def test_an_empty_document_is_none(self):
        assert load_yaml(io.StringIO(""), source="empty.yaml") is None


class TestCrossFactEdges:
    def _engine(self, *patterns: Any) -> Any:
        from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule

        engine = CrossFactEngine()
        engine.load_rules([CrossFactRule(id=1, name="r", patterns=list(patterns), action="a")])
        return engine

    def test_a_quantifier_skips_the_fact_already_bound(self):
        from fluxrules.engine.cross_fact import Exists, Pattern

        # "A paid order with no other paid order": the bound order itself does
        # not count as the other one.
        engine = self._engine(
            Pattern("o", "Order", constraints=[("status", "==", "paid")]),
            Exists(fact_type="Order", constraints=[("status", "==", "paid")], negated=True),
        )
        engine.insert("Order", {"id": 1, "status": "paid"})
        assert len(engine.activations()) == 1
        engine.insert("Order", {"id": 2, "status": "paid"})
        assert engine.activations() == []

    def test_a_join_on_an_unbound_variable_matches_nothing(self):
        from fluxrules.engine.cross_fact import Exists, Pattern

        engine = self._engine(
            Pattern("o", "Order", constraints=[("status", "==", "paid")]),
            Exists(fact_type="Shipment", joins=[("order_id", "==", "nobody", "id")]),
        )
        engine.insert("Order", {"id": 1, "status": "paid"})
        engine.insert("Shipment", {"order_id": 1})
        assert engine.activations() == []

    def test_an_accumulate_threshold_that_cannot_be_compared_is_reported(self):
        from fluxrules.engine.cross_fact import Accumulate, Pattern

        set_config(EngineConfig(uncomparable="raise"))
        engine = self._engine(
            Pattern("c", "Customer"),
            Accumulate(
                "n",
                "Order",
                "count",
                joins=[("customer_id", "==", "c", "id")],
                having=(">", "many"),
            ),
        )
        with pytest.raises(UncomparableValuesError):
            engine.insert("Customer", {"id": 1})


class Account(BaseModel):
    amount: float
    total: Decimal
    vip: bool


class TestSecondReviewFixes:
    def test_approx_needs_a_numeric_target_on_a_number_field(self):
        engine = PhreakEngine(fact_schema=Account)
        with pytest.raises(RuleValueError, match="Write 10 without quotes"):
            engine.load_rules([_rule(F("amount").approx("10"))])

    def test_approx_text_on_a_decimal_field_loads_as_a_decimal(self):
        engine = PhreakEngine(fact_schema=Account)
        engine.load_rules([_rule(F("total").approx("10.10", abs_tol=0.01))])
        (rule,) = engine.rule_repository.rules.values()
        assert rule.conditions["value"] == {"value": Decimal("10.10"), "abs_tol": 0.01}
        fact = {"amount": 1.0, "total": Decimal("10.105"), "vip": False}
        assert engine.evaluate(fact).fired_rules == [1]

    def test_boolean_text_in_a_list_is_converted_under_coercion(self):
        config = EngineConfig(boolean_string_coercion=True)
        engine = PhreakEngine(fact_schema=Account, config=config)
        engine.load_rules([_rule(F("vip").isin(["true"]))])
        (rule,) = engine.rule_repository.rules.values()
        assert rule.conditions["value"] == [True]
        fact = {"amount": 1.0, "total": Decimal(1), "vip": True}
        assert engine.evaluate(fact).fired_rules == [1]

    def test_low_level_batch_workers_get_the_process_config(self):
        from fluxrules.engine.runtime.worker_pool import evaluate_batch_parallel

        set_config(EngineConfig(uncomparable="unknown"))
        rules = [_rule(~(F("v") > 5))]
        facts = [{"v": "abc"}, {"v": 1}, {"v": "abc"}, {"v": 1}]
        # Under "unknown", NOT over "abc" > 5 does not fire; over 1 > 5 it does.
        assert evaluate_batch_parallel(rules, facts, num_workers=2) == [[], [1], [], [1]]


class TestThirdReviewFixes:
    @pytest.mark.parametrize(
        ("condition", "message"),
        [
            (F("country").equals_ignore_case(7), 'Write "7" in quotes'),
            (F("country").in_ignore_case(["NO", 7]), "compares it with the number 7"),
            (F("country").starts_with_ignore_case(None), "compares it with None"),
        ],
    )
    def test_ignore_case_operands_must_be_text_on_a_text_field(self, condition, message):
        with pytest.raises(RuleValueError, match=message):
            PhreakEngine(fact_schema=Event).load_rules([_rule(condition)])

    def test_text_operands_load(self):
        PhreakEngine(fact_schema=Event).load_rules(
            [_rule(F("country").in_ignore_case(["no", "se"]))]
        )
