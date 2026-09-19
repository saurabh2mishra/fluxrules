"""Pin the flat-fact contract of the PHREAK engine.

Audit 04 (M1) noted an ambiguity: FluxRules supports nested *condition trees*
(AND/OR/NOT groups), but it does not perform nested *fact traversal*. Each
condition leaf reads a fact by exact key via ``facts.get(field)``. Nested input
must be pre-flattened (for example to dotted keys) before evaluation.

These tests pin that contract so documentation and implementation cannot
silently drift apart.
"""

from __future__ import annotations

import pytest

from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine


def _engine(cls, field: str):
    engine = cls()
    engine.load_rules(
        [
            Rule(
                id=1,
                name="deep_age",
                condition_dsl={
                    "type": "condition",
                    "field": field,
                    "op": ">",
                    "value": 18,
                },
                persist=False,
            )
        ]
    )
    return engine


@pytest.mark.parametrize("cls", [PhreakEngine])
def test_flattened_dotted_key_matches(cls):
    """A pre-flattened dotted key is a plain field name and matches exactly."""
    engine = _engine(cls, "user.profile.age")
    assert engine.evaluate({"user.profile.age": 25}).fired_rules == [1]
    assert engine.evaluate({"user.profile.age": 10}).fired_rules == []


@pytest.mark.parametrize("cls", [PhreakEngine])
def test_nested_dict_is_not_traversed(cls):
    """A nested dict is not traversed: the dotted field is simply absent."""
    engine = _engine(cls, "user.profile.age")
    # The value lives inside a nested dict, not under the exact dotted key.
    assert engine.evaluate({"user": {"profile": {"age": 25}}}).fired_rules == []
