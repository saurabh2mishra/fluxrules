"""Validators must accept exactly what the engines execute.

Two validators inspect `condition_dsl`, and both had drifted away from the
engines they are supposed to guard. The drift was invisible because each
validator's own tests only exercised the vocabulary it happened to accept - so
the shapes it wrongly rejected were never tried, and the shapes it silently
skipped were never noticed.

The two failure directions are not equally visible, and both were present:

* **too strict** - rejecting a valid rule. Loud, but wrong: `StructuralValidator`
  hardcoded 10 operators while the engines accept 19, so a rule using `gt` or
  `regex` was refused by the strict gateway.
* **too lax** - accepting anything, including genuinely broken rules. Silent.
  `StructuralValidator` recognised only `group`, so an `and` node fell through
  to the "unknown type" branch, which returns *without inspecting the subtree* -
  every condition nested inside it went unvalidated. That bug also masked the
  operator bug, which is why neither surfaced in normal use.

These tests derive their expectations from the engine's own operator registry
rather than restating a list, so a validator cannot drift from it again without
failing here.
"""

from __future__ import annotations

import pytest

from fluxrules.engine.operators import VALID_OPERATORS

#: Every boolean node shape a rule can legitimately arrive in. `and`/`or` are
#: what the engines evaluate; `group`/`composite` are the authoring shapes;
#: children live under either "children" or "conditions" depending on the
#: producer. A validator that recognises only some of these does not reject the
#: rest - it skips them.
LEAF = {"type": "condition", "field": "amount", "op": "gt", "value": 100}

BOOLEAN_SHAPES = {
    "and/children": {"type": "and", "children": [LEAF]},
    "or/children": {"type": "or", "children": [LEAF]},
    "group/children": {"type": "group", "op": "AND", "children": [LEAF]},
    "composite/conditions": {"type": "composite", "op": "AND", "conditions": [LEAF]},
    "not/children": {"type": "not", "children": [LEAF]},
    "not/condition": {"type": "not", "condition": LEAF},
    "nested and>or": {"type": "and", "children": [{"type": "or", "children": [LEAF]}]},
}


class TestStructuralValidatorTracksTheEngine:
    """The validator wired into `ValidationGateway`, i.e. the live one."""

    def _validate(self, dsl):
        from fluxrules.services.validators.structural_validator import (
            StructuralValidator,
        )

        return StructuralValidator().validate({"name": "r", "condition_dsl": dsl, "action": "flag"})

    @pytest.mark.parametrize("name", sorted(BOOLEAN_SHAPES))
    def test_every_boolean_shape_is_accepted(self, name: str) -> None:
        result = self._validate(BOOLEAN_SHAPES[name])
        assert not result.has_errors(), [i.message for i in result.get_errors()]

    @pytest.mark.parametrize("name", sorted(BOOLEAN_SHAPES))
    def test_no_boolean_shape_is_reported_as_unknown(self, name: str) -> None:
        """An 'unknown type' warning means the subtree was never inspected."""
        result = self._validate(BOOLEAN_SHAPES[name])
        assert not any("Unknown DSL type" in issue.message for issue in result.get_warnings())

    @pytest.mark.parametrize("operator", sorted(VALID_OPERATORS))
    def test_every_engine_operator_is_accepted(self, operator: str) -> None:
        """Sourced from the registry: a hardcoded copy is what drifted before."""
        result = self._validate({"type": "condition", "field": "a", "op": operator, "value": 1})
        assert not result.has_errors(), [i.message for i in result.get_errors()]

    def test_a_bad_operator_inside_an_and_is_still_caught(self) -> None:
        """The regression: errors nested under `and` were skipped entirely."""
        result = self._validate(
            {
                "type": "and",
                "children": [
                    {
                        "type": "condition",
                        "field": "a",
                        "op": "definitely_not",
                        "value": 1,
                    }
                ],
            }
        )
        assert result.has_errors()

    def test_a_missing_field_inside_an_and_is_still_caught(self) -> None:
        result = self._validate(
            {"type": "and", "children": [{"type": "condition", "op": "gt", "value": 1}]}
        )
        assert result.has_errors()

    def test_an_empty_boolean_node_is_still_rejected(self) -> None:
        result = self._validate({"type": "and", "children": []})
        assert result.has_errors()

    def test_a_genuinely_unknown_type_is_still_reported(self) -> None:
        """Loosening the vocabulary must not turn it into 'accept anything'."""
        result = self._validate({"type": "wibble"})
        assert any("Unknown DSL type" in issue.message for issue in result.get_warnings())


class TestStrictValidateDslTracksTheEngine:
    """`validate_dsl` - stricter, opt-in, and not currently on a write path.

    It is kept aligned regardless: it is exported, tested, and the obvious
    thing to reach for when adding validation to an ingestion path. A strict
    validator that rejects the product's own rule shapes is a trap for whoever
    wires it in next.
    """

    def _validate(self, dsl):
        from fluxrules.domain.dsl.validation import validate_dsl

        return validate_dsl(dsl)

    @pytest.mark.parametrize("name", sorted(BOOLEAN_SHAPES))
    def test_every_boolean_shape_is_accepted(self, name: str) -> None:
        self._validate(BOOLEAN_SHAPES[name])  # must not raise

    @pytest.mark.parametrize("operator", sorted(VALID_OPERATORS))
    def test_every_engine_operator_is_accepted(self, operator: str) -> None:
        self._validate({"type": "condition", "field": "a", "op": operator, "value": 1})

    @pytest.mark.parametrize(
        "dsl",
        [
            pytest.param(
                {
                    "type": "and",
                    "children": [{"type": "condition", "field": "a", "op": "nope", "value": 1}],
                },
                id="bad-operator-nested",
            ),
            pytest.param({"type": "and", "children": []}, id="empty-children"),
            pytest.param({"type": "wibble"}, id="unknown-type"),
            pytest.param({"type": "condition", "field": "a"}, id="missing-op"),
            pytest.param(
                {"type": "condition", "field": "a", "op": "gt", "value": 1, "typo": 1},
                id="unknown-key",
            ),
        ],
    )
    def test_invalid_dsl_is_still_rejected(self, dsl) -> None:
        from fluxrules.domain.dsl.validation import DSLValidationError

        with pytest.raises(DSLValidationError):
            self._validate(dsl)


def test_the_two_validators_agree_on_the_shapes_they_both_see() -> None:
    """Disagreement is how a rule passes one gate and fails another.

    They differ in strictness by design - `validate_dsl` also checks for
    unknown keys - but they must not disagree about whether a *well-formed*
    rule is valid.
    """
    from fluxrules.domain.dsl.validation import validate_dsl
    from fluxrules.services.validators.structural_validator import StructuralValidator

    for name, dsl in BOOLEAN_SHAPES.items():
        structural = StructuralValidator().validate(
            {"name": "r", "condition_dsl": dsl, "action": "flag"}
        )
        assert not structural.has_errors(), name
        validate_dsl(dsl)  # must not raise
