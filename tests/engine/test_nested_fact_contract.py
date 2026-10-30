"""Pin the flat-fact contract of the PHREAK engine.

Audit 04 (M1) noted an ambiguity: FluxRules supports nested *condition trees*
(AND/OR/NOT groups), but it does not perform nested *fact traversal*. Each
condition leaf reads a fact by exact key via ``facts.get(field)``. Nested input
must be pre-flattened (for example to dotted keys) before evaluation.

Since 1.1.0 an unflattened nested value is reported instead of silently not
matching: a rule on ``user.profile.age`` against ``{"user": {...}}`` raises
``FieldNotFoundError`` with a hint to flatten the fact.

These tests pin that contract so documentation and implementation cannot
silently drift apart.
"""

from __future__ import annotations

import pytest

from fluxrules import FieldNotFoundError, Rule
from fluxrules.engine.phreak import PhreakEngine


def _engine(cls, field: str):
    engine = cls()
    engine.load_rules(
        [
            Rule(
                id=1,
                name="deep_age",
                conditions={
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
    """A nested dict is not traversed, and the unflattened fact is reported."""
    engine = _engine(cls, "user.profile.age")
    # The value lives inside a nested dict, not under the exact dotted key.
    with pytest.raises(FieldNotFoundError, match="flatten"):
        engine.evaluate({"user": {"profile": {"age": 25}}})


@pytest.mark.parametrize("cls", [PhreakEngine])
def test_unrelated_absent_dotted_field_stays_silent(cls):
    """A dotted field whose parent is absent is just absent: no error."""
    engine = _engine(cls, "user.profile.age")
    assert engine.evaluate({"order": 1}).fired_rules == []
