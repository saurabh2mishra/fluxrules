"""A single ``in`` / ``not_in`` value is a one-item list on every path.

``F("country").isin("US")`` means "country is one of ["US"]". Python's ``in``
on a string would test for a substring, so ``"U"`` used to count as a member
of ``"US"`` on some paths and not on others. The value is now wrapped in a list
when the rule is created, with a ``MembershipValueWarning`` for the author, and
the operator and the alpha prefilter treat a single value the same way.
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import F, MembershipValueWarning, Rule, evaluate
from fluxrules.domain.conditions.evaluator import evaluate_conditions
from fluxrules.domain.conditions.membership import normalize_membership_values
from fluxrules.domain.models import EngineRule
from fluxrules.engine.phreak import PhreakEngine

ENGINE_OPTIONS = [
    pytest.param({}, id="engine"),
    pytest.param({"alpha_prefilter": False}, id="no-prefilter"),
    pytest.param({"compile_conditions": True}, id="compiled"),
    pytest.param({"streaming_mode": True}, id="streaming"),
]

# (op, rule value, fact value, should fire)
TABLE = [
    ("in", ["US", "DE"], "U", False),
    ("in", ["US", "DE"], "US", True),
    ("in", ["US", "DE"], "", False),
    ("in", "US", "U", False),
    ("in", "US", "US", True),
    ("in", "US", "", False),
    ("not_in", ["US", "DE"], "U", True),
    ("not_in", ["US", "DE"], "US", False),
    ("not_in", ["US", "DE"], "", True),
    ("not_in", "US", "U", True),
    ("not_in", "US", "US", False),
    ("not_in", "US", "", True),
    ("in", 5, 5, True),
    ("in", 5, 1, False),
    ("not_in", 5, 1, True),
]
TABLE_IDS = [f"{op} {value!r} fact {fact!r}" for op, value, fact, _ in TABLE]


def _condition(op, value):
    return {"type": "condition", "field": "country", "op": op, "value": value}


def _rule(op, value):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MembershipValueWarning)
        return Rule(id=1, name="r", conditions=_condition(op, value), action="hit")


@pytest.mark.parametrize("options", ENGINE_OPTIONS)
@pytest.mark.parametrize(("op", "value", "fact", "fires"), TABLE, ids=TABLE_IDS)
def test_engine_paths_agree(options, op, value, fact, fires):
    engine = PhreakEngine(**options)
    engine.load_rules([_rule(op, value)])
    assert bool(engine.evaluate({"country": fact}).fired_rules) is fires


@pytest.mark.parametrize(("op", "value", "fact", "fires"), TABLE, ids=TABLE_IDS)
def test_evaluate_agrees(op, value, fact, fires):
    assert bool(evaluate(_rule(op, value), {"country": fact}).fired_rules) is fires


@pytest.mark.parametrize(("op", "value", "fact", "fires"), TABLE, ids=TABLE_IDS)
def test_raw_condition_dict_agrees(op, value, fact, fires):
    """A raw dict is never normalised, so the operator itself must agree."""
    assert evaluate_conditions(_condition(op, value), {"country": fact}) is fires


@pytest.mark.parametrize(("op", "single"), [("in", "=="), ("not_in", "!=")])
def test_f_expression_warns_at_the_authors_line_and_stores_a_list(op, single):
    method = F("country").isin if op == "in" else F("country").not_in
    with pytest.warns(MembershipValueWarning) as record:
        condition = method("US")
    assert condition.to_dict()["value"] == ["US"]
    assert len(record) == 1
    assert record[0].filename == __file__
    message = str(record[0].message)
    assert "'country'" in message
    assert f"'{op}' expects a list" in message
    assert "treated as ['US']" in message
    assert f"'{single}'" in message


def test_rule_from_dict_warns_with_the_tree_path():
    tree = {
        "type": "not",
        "condition": {
            "type": "group",
            "op": "OR",
            "children": [
                {"type": "condition", "field": "x", "op": "==", "value": 1},
                _condition("not_in", "US"),
            ],
        },
    }
    with pytest.warns(MembershipValueWarning, match=r"root\.condition\.children\[1\]") as record:
        rule = Rule(id=1, name="r", conditions=tree, action="a")
    assert record[0].filename == __file__
    assert rule.conditions["condition"]["children"][1]["value"] == ["US"]
    assert tree["condition"]["children"][1]["value"] == "US", "the input is not modified"


def test_a_list_tuple_or_set_is_left_alone_without_a_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", MembershipValueWarning)
        for value in (["US"], ("US",), {"US"}, frozenset({"US"})):
            Rule(id=1, name="r", conditions=_condition("in", value), action="a")
            F("country").isin(value)


def test_the_warning_fires_once_per_rule_not_on_every_conversion():
    with pytest.warns(MembershipValueWarning) as record:
        rule = Rule(
            id=1,
            name="r",
            conditions=F("country").isin(["US"]) | _condition("in", "DE"),
            action="a",
        )
        rule.to_engine_rule()
        PhreakEngine().load_rules([rule])
        evaluate(rule, {"country": "DE"})
    assert len(record) == 1


def test_rules_read_back_from_storage_are_normalised():
    with pytest.warns(MembershipValueWarning):
        engine_rule = EngineRule(id=1, name="r", conditions=_condition("in", "US"))
    assert engine_rule.conditions["value"] == ["US"]


def test_normalize_returns_the_same_tree_when_nothing_changes():
    tree = {"type": "group", "op": "AND", "children": [_condition("in", ["US"])]}
    assert normalize_membership_values(tree) is tree


def test_normalize_can_skip_the_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tree = normalize_membership_values(_condition("in", "US"), warn=False)
    assert tree["value"] == ["US"]


def test_normalize_passes_malformed_trees_through():
    # Plain values in a list are left for the validator to report.
    items = ["US", 1, None]
    assert normalize_membership_values(items, warn=False) is items
    # Every changed child of one node lands in the same copy.
    tree = {"left": _condition("in", "US"), "right": _condition("not_in", "DE")}
    out = normalize_membership_values(tree, warn=False)
    assert (out["left"]["value"], out["right"]["value"]) == (["US"], ["DE"])
    assert tree["left"]["value"] == "US", "the input is not modified"


# (rule value, fact value, should fire): members that cannot be hashed
UNHASHABLE = [
    ([{"a": 1}], {"a": 1}, True),
    ([{"a": 1}], {"a": 2}, False),
    ([[1, 2]], [1, 2], True),
    ([[1, 2]], [2, 1], False),
    ([{"a": 1}, "US"], "US", True),
    ([{"a": 1}, "US"], "DE", False),
]


@pytest.mark.parametrize("options", ENGINE_OPTIONS)
@pytest.mark.parametrize(
    ("value", "fact", "fires"),
    UNHASHABLE,
    ids=[f"in {v!r} fact {f!r}" for v, f, _ in UNHASHABLE],
)
def test_unhashable_members_load_and_match_by_equality(options, value, fact, fires):
    """The alpha prefilter falls back to ``==`` membership instead of raising."""
    engine = PhreakEngine(**options)
    engine.load_rules([_rule("in", value)])
    assert bool(engine.evaluate({"country": fact}).fired_rules) is fires


def test_a_single_dict_is_a_one_item_list():
    with pytest.warns(MembershipValueWarning):
        rule = Rule(id=1, name="r", conditions=_condition("in", {"a": 1}), action="hit")
    assert rule.conditions["value"] == [{"a": 1}]
    engine = PhreakEngine()
    engine.load_rules([rule])
    assert engine.evaluate({"country": {"a": 1}}).fired_rules == [1]
    assert engine.evaluate({"country": "a"}).fired_rules == [], "not a key lookup"
