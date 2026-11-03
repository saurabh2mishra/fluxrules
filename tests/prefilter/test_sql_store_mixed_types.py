"""The SQL fact store never drops a fact the engine would fire on.

The store used to keep only numbers in its columns, so a present text value
looked like a missing field: an OR rule over text values, a boolean against a
number, or a ``Decimal`` lost the fact, and a ``Decimal`` crashed the JSON
payload. A present value that SQL cannot compare exactly now always keeps its
row, and the payload round-trips every supported type.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine  # noqa: E402

from fluxrules import F, Rule  # noqa: E402
from fluxrules.engine.phreak import PhreakEngine  # noqa: E402
from fluxrules.prefilter import PreFilteredEvaluator  # noqa: E402
from fluxrules.prefilter.sql_store import (  # noqa: E402
    FactPreFilterStore,
    decode_fact,
    encode_fact,
)


def _run(condition, facts):
    engine = PhreakEngine()
    engine.load_rules([Rule(id=1, name="r", conditions=condition, action="hit")])
    store = FactPreFilterStore(engine=create_engine("sqlite://"))
    try:
        results, stats = PreFilteredEvaluator(engine, store).run(facts)
    finally:
        store.dispose()
    expected = sum(bool(engine.evaluate(f).fired_rules) for f in facts)
    return len(results), expected, stats


@pytest.mark.parametrize(
    ("condition", "fact"),
    [
        pytest.param((F("x") == "a") | (F("x") == "b"), {"x": "a"}, id="OR over text values"),
        pytest.param((F("x") > 5) | (F("x") == "vip"), {"x": "vip"}, id="OR of number and text"),
        pytest.param(F("x") > 0, {"x": True}, id="bool against a number"),
        pytest.param(F("x") > 5, {"x": Decimal("7")}, id="Decimal against a number"),
        pytest.param(F("x") > 2**53, {"x": 2**53 + 1}, id="int beyond 2**53"),
        pytest.param(F("x") == 5, {"x": Decimal("5")}, id="Decimal equal to a number"),
    ],
)
def test_facts_the_engine_fires_on_are_kept(condition, fact):
    fired, expected, _ = _run(condition, [fact])
    assert expected == 1
    assert fired == 1


def test_facts_that_cannot_match_are_still_screened_out():
    fired, expected, stats = _run(F("x") > 5, [{"x": 7}, {"x": 3}, {"y": 1}])
    assert (fired, expected) == (1, 1)
    assert stats.candidate_facts == 1, "3 and the missing field must not reach the engine"


def test_a_rule_value_sql_cannot_compare_exactly_is_not_used_to_screen():
    fired, expected, stats = _run(F("x") > 2**60, [{"x": 2**60 + 1}, {"x": 1}])
    assert (fired, expected) == (1, 1)
    assert stats.candidate_facts == 2


@pytest.mark.parametrize(
    "fact",
    [
        {"amount": Decimal("10.50"), "id": 7, "rate": 0.25, "ok": True, "note": None},
        {"day": date(2026, 6, 1), "at": datetime(2026, 6, 1, 12, 30), "t": time(9, 15)},
        {"pair": (1, "a"), "tags": {"x", "y"}, "frozen": frozenset({1}), "items": [1, (2, 3)]},
        {"nested": {"inner": Decimal("1.1"), "__fluxrules_type__": "user data"}},
        {"big": 2**70, "text": "Ünïcode"},
    ],
)
def test_the_payload_round_trips_exactly(fact):
    restored = decode_fact(encode_fact(fact))
    assert restored == fact
    assert {k: type(v) for k, v in restored.items()} == {k: type(v) for k, v in fact.items()}


def test_nan_and_inf_round_trip():
    restored = decode_fact(encode_fact({"a": math.nan, "b": math.inf}))
    assert math.isnan(restored["a"]) and restored["b"] == math.inf


@pytest.mark.parametrize(
    ("fact", "message"),
    [
        ({"x": object()}, "fact field 'x' holds a object"),
        ({"x": {1: "a"}}, "fact field 'x' has a non-string key 1"),
        ({1: "a"}, "non-string field name 1"),
    ],
)
def test_values_the_store_cannot_save_raise_a_clear_error(fact, message):
    with pytest.raises(TypeError, match=message):
        encode_fact(fact)
