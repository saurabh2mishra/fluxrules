"""Pin the explanation-string contract of the PHREAK engine.

Audit 04 (M2) noted that explanations are engine-specific summary strings for
fired rules, not condition-level traces. These tests pin the documented
contract:

* ``explanations`` contains an entry only for fired rules.
* Each explanation is a human-readable string mentioning the engine.
"""

from __future__ import annotations

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _rules():
    return [
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


def test_phreak_explanation_only_for_fired_rules():
    engine = PhreakEngine()
    engine.load_rules(_rules())

    fired = engine.evaluate({"amount": 500})
    assert fired.fired_rules == [1]
    assert set(fired.explanations) == {1}
    assert "PHREAK" in fired.explanations[1]

    not_fired = engine.evaluate({"amount": 50})
    assert not_fired.fired_rules == []
    assert not_fired.explanations == {}


def test_phreak_explanation_mentions_engine():
    engine = PhreakEngine()
    engine.load_rules(_rules())

    fired = engine.evaluate({"amount": 500})
    assert fired.fired_rules == [1]
    assert "PHREAK" in fired.explanations[1]
