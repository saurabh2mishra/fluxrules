"""evaluate() and PhreakEngine give the same answer for every operator.

The top-level ``evaluate()`` runs the reference evaluator, whose operators live in
``fluxrules.domain.predicates``. ``PhreakEngine`` calls
``fluxrules.engine.operators.evaluate_operator``. The reference table delegates to
the engine function, so the two must agree, including on ``None`` values, type
mismatches and invalid regex patterns.

The engine runs with ``alpha_prefilter=False`` here so the comparison is between
the two operator implementations only, not the prefilter.
"""

from __future__ import annotations

import pytest

from fluxrules import F, Rule, evaluate
from fluxrules.domain.predicates import OPERATORS
from fluxrules.engine.operators import VALID_OPERATORS
from fluxrules.engine.phreak import PhreakEngine


def _evaluate(rule: Rule, fact: dict) -> list[int]:
    return evaluate(rule, fact).fired_rules


def _phreak(rule: Rule, fact: dict) -> list[int]:
    engine = PhreakEngine(alpha_prefilter=False)
    engine.load_rules([rule])
    return engine.evaluate(fact).fired_rules


def test_reference_table_covers_every_engine_operator():
    assert set(OPERATORS) == set(VALID_OPERATORS)


# (case id, condition, fact, expected fired rule ids)
CASES = [
    # one matching and one non-matching fact per operator
    ("== hit", F("n") == 5, {"n": 5}, [1]),
    ("== miss", F("n") == 5, {"n": 6}, []),
    ("!= hit", F("n") != 5, {"n": 6}, [1]),
    ("> hit", F("n") > 5, {"n": 6}, [1]),
    ("> miss", F("n") > 5, {"n": 5}, []),
    (">= hit", F("n") >= 5, {"n": 5}, [1]),
    ("< hit", F("n") < 5, {"n": 4}, [1]),
    ("<= hit", F("n") <= 5, {"n": 5}, [1]),
    ("in hit", F("n").isin([1, 5]), {"n": 5}, [1]),
    ("in miss", F("n").isin([1, 5]), {"n": 2}, []),
    ("not_in hit", F("n").not_in([1, 5]), {"n": 2}, [1]),
    ("contains hit", F("s").contains("ell"), {"s": "hello"}, [1]),
    ("not_contains hit", F("s").not_contains("ell"), {"s": "world"}, [1]),
    ("starts_with hit", F("s").starts_with("he"), {"s": "hello"}, [1]),
    ("starts_with miss", F("s").starts_with("he"), {"s": "world"}, []),
    ("ends_with hit", F("s").ends_with("lo"), {"s": "hello"}, [1]),
    ("ends_with miss", F("s").ends_with("lo"), {"s": "world"}, []),
    ("regex anchored hit", F("s").regex("^h.l"), {"s": "hello"}, [1]),
    ("regex searches anywhere", F("s").regex("ell"), {"s": "hello"}, [1]),
    ("regex miss", F("s").regex("^w"), {"s": "hello"}, []),
    # string operators convert non-strings
    ("starts_with on an int", F("code").starts_with("12"), {"code": 1234}, [1]),
    # a None value never matches by default, even where str(None) would
    ("starts_with on None", F("s").starts_with("No"), {"s": None}, []),
    ("regex on None", F("s").regex("None"), {"s": None}, []),
    ("== None on None", F("s") == None, {"s": None}, []),  # noqa: E711
    ("!= on None", F("s") != 1, {"s": None}, []),
    # type mismatches return no match instead of raising
    ("contains on an int", F("s").contains("a"), {"s": 5}, []),
    ("> on a string", F("s") > 5, {"s": "x"}, []),
    ("isin with a non-list", F("s").isin(5), {"s": 1}, []),
    ("invalid regex pattern", F("s").regex("("), {"s": "x"}, []),
    # a missing field that is not a typo of a present key
    ("missing field", F("absent") > 5, {"other": 1}, []),
]


@pytest.mark.parametrize(("case", "condition", "fact", "expected"), CASES, ids=[c[0] for c in CASES])
def test_evaluate_and_phreak_agree(case, condition, fact, expected):
    rule = Rule(id=1, name="r", conditions=condition, action="a")
    assert _evaluate(rule, fact) == expected
    assert _phreak(rule, fact) == expected


@pytest.mark.parametrize(
    ("alias", "symbol"),
    [("eq", "=="), ("ne", "!="), ("gt", ">"), ("gte", ">="), ("lt", "<"), ("lte", "<=")],
)
def test_word_aliases_match_symbols_through_evaluate(alias, symbol):
    for fact_value in (4, 5, 6):
        fact = {"n": fact_value}
        by_alias = Rule(
            id=1,
            name="r",
            conditions={"type": "condition", "field": "n", "op": alias, "value": 5},
            action="a",
        )
        by_symbol = Rule(
            id=1,
            name="r",
            conditions={"type": "condition", "field": "n", "op": symbol, "value": 5},
            action="a",
        )
        assert _evaluate(by_alias, fact) == _evaluate(by_symbol, fact)
        assert _phreak(by_alias, fact) == _phreak(by_symbol, fact)
