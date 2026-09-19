"""Pin the single-fact evaluation contract of the PHREAK engine.

Audit 04 (C3) found documentation claiming that the engine keeps a
match-driving working memory: that ``assert_fact`` propagates facts into
subsequent matches. In reality ``assert_fact`` / ``retract_fact`` are storage
only, and ``evaluate`` matches solely the fact map passed to it. These tests pin
that contract so the documentation cannot silently drift back.
"""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _engine(cls):
    engine = cls()
    engine.load_rules(
        [
            Rule(
                id=1,
                name="high_value",
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 100,
                },
                persist=False,
            )
        ]
    )
    return engine


@pytest.mark.parametrize("cls", [PhreakEngine])
def test_assert_fact_does_not_drive_evaluate(cls):
    engine = _engine(cls)

    # Storing a matching fact must NOT make an empty evaluate fire the rule.
    fact_id = engine.assert_fact({"amount": 500})
    assert isinstance(fact_id, str)
    assert engine.evaluate({}).fired_rules == []

    # Only the fact map passed to evaluate drives matching.
    assert engine.evaluate({"amount": 500}).fired_rules == [1]
    assert engine.evaluate({"amount": 50}).fired_rules == []


@pytest.mark.parametrize("cls", [PhreakEngine])
def test_selectable_engines_expose_no_session_or_wm_evaluation(cls):
    engine = cls()
    # These match-driving working-memory APIs are intentionally absent; sessions
    # live in the service layer (RuleService.create_session).
    assert not hasattr(engine, "create_session")
    assert not hasattr(engine, "evaluate_working_memory")
