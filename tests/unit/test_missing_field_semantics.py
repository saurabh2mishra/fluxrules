"""Missing-field semantics for NOT (EngineConfig.missing_field).

A missing field makes its condition False. Under NOT that used to invert to
True, so ``~(F("blocked") == True)`` fired on a fact with no ``blocked`` key.
``missing_field`` selects the behaviour:

- ``"false"``: the 1.x behaviour, silently.
- ``None`` (default): the 1.x behaviour, plus a MissingFieldNotWarning.
- ``"unknown"``: Kleene three-valued logic; a NOT over unknown does not fire.

Every evaluator must agree: the PHREAK interpreter, the compiled closures and
the reference evaluator behind ``fluxrules.evaluate``.
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import EngineConfig, F, MissingFieldNotWarning, Rule, evaluate
from fluxrules.domain.conditions.missing_fields import evaluate_tristate, leaf_fields
from fluxrules.engine.configuration import get_config, set_config
from fluxrules.engine.phreak import PhreakEngine


def _rule(conditions):
    return Rule(id=1, name="r", conditions=conditions, action="flag")


@pytest.fixture
def global_mode():
    """Set the process-wide config (used by fluxrules.evaluate), then restore it."""
    previous = get_config()

    def _set(mode):
        set_config(EngineConfig(missing_field=mode))

    yield _set
    set_config(previous)


def _fires(conditions, facts, mode, path, global_mode):
    """Evaluate on one path and return whether the rule fired (warnings ignored)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MissingFieldNotWarning)
        if path == "evaluate":
            global_mode(mode)
            return evaluate(_rule(conditions), facts).fired_rules == [1]
        engine = PhreakEngine(
            config=EngineConfig(missing_field=mode),
            compile_conditions=(path == "compiled"),
        )
        engine.load_rules([_rule(conditions)])
        return engine.evaluate(facts).fired_rules == [1]


PATHS = ["interpreted", "compiled", "evaluate"]

NOT_BLOCKED = ~(F("blocked") == True)  # noqa: E712

# (conditions, facts, fires under "false"/None, fires under "unknown")
CASES = [
    pytest.param(NOT_BLOCKED, {"amount": 1}, True, False, id="not-missing"),
    pytest.param(NOT_BLOCKED, {"blocked": False}, True, True, id="not-present-false"),
    pytest.param(NOT_BLOCKED, {"blocked": True}, False, False, id="not-present-true"),
    # NOT(A AND B), A definitely false: AND is false whatever B is -> NOT fires.
    pytest.param(~((F("a") == 1) & (F("b") == 1)), {"a": 2}, True, True, id="not-and-definite"),
    # NOT(A AND B), A true, B missing: AND is unknown -> NOT does not fire.
    pytest.param(~((F("a") == 1) & (F("b") == 1)), {"a": 1}, True, False, id="not-and-unknown"),
    # NOT(A OR B), A true: OR is true -> NOT false in every mode.
    pytest.param(~((F("a") == 1) | (F("b") == 1)), {"a": 1}, False, False, id="not-or-true"),
    # NOT(A OR B), A false, B missing: OR unknown -> NOT does not fire.
    pytest.param(~((F("a") == 1) | (F("b") == 1)), {"a": 2}, True, False, id="not-or-unknown"),
    # Double negation of a missing field: unknown stays unknown.
    pytest.param(~~(F("a") == 1), {"z": 1}, False, False, id="double-not"),
    # exists() is never unknown: ~exists fires on absence in every mode.
    pytest.param(~F("blocked").exists(), {"amount": 1}, True, True, id="not-exists"),
    # Explicit absence check plus value check, the recommended rewrite.
    pytest.param(
        ~F("blocked").exists() | ~(F("blocked") == True),  # noqa: E712
        {"amount": 1},
        True,
        True,
        id="explicit-absence",
    ),
    # AND with a NOT over a missing field next to a satisfied leaf.
    pytest.param((F("a") == 1) & NOT_BLOCKED, {"a": 1}, True, False, id="and-with-not"),
]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize(("conditions", "facts", "legacy", "unknown"), CASES)
class TestModesAgreeAcrossEvaluators:
    def test_false_mode(self, conditions, facts, legacy, unknown, path, global_mode):
        assert _fires(conditions, facts, "false", path, global_mode) is legacy

    def test_default_mode_matches_legacy(
        self, conditions, facts, legacy, unknown, path, global_mode
    ):
        assert _fires(conditions, facts, None, path, global_mode) is legacy

    def test_unknown_mode(self, conditions, facts, legacy, unknown, path, global_mode):
        assert _fires(conditions, facts, "unknown", path, global_mode) is unknown


class TestWarning:
    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_default_mode_warns_when_not_fires_on_missing_field(self, compile_conditions):
        engine = PhreakEngine(compile_conditions=compile_conditions)
        engine.load_rules([_rule(NOT_BLOCKED)])
        with pytest.warns(MissingFieldNotWarning, match="blocked"):
            assert engine.evaluate({"amount": 1}).fired_rules == [1]

    def test_no_warning_when_field_present(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(NOT_BLOCKED)])
        with warnings.catch_warnings():
            warnings.simplefilter("error", MissingFieldNotWarning)
            assert engine.evaluate({"blocked": False}).fired_rules == [1]

    def test_no_warning_when_result_is_definite(self):
        # NOT(a==1 AND b==1) with a=2 fires in every mode: nothing to warn about.
        engine = PhreakEngine()
        engine.load_rules([_rule(~((F("a") == 1) & (F("b") == 1)))])
        with warnings.catch_warnings():
            warnings.simplefilter("error", MissingFieldNotWarning)
            assert engine.evaluate({"a": 2}).fired_rules == [1]

    @pytest.mark.parametrize("mode", ["false", "unknown"])
    def test_explicit_mode_is_silent(self, mode):
        engine = PhreakEngine(config=EngineConfig(missing_field=mode))
        engine.load_rules([_rule(NOT_BLOCKED)])
        with warnings.catch_warnings():
            warnings.simplefilter("error", MissingFieldNotWarning)
            engine.evaluate({"amount": 1})

    def test_warning_is_a_future_warning(self):
        assert issubclass(MissingFieldNotWarning, FutureWarning)
        assert MissingFieldNotWarning.code == "MISSING_FIELD_NOT"


class TestConfig:
    def test_default_is_none(self):
        assert EngineConfig().missing_field is None

    def test_rejects_unknown_mode(self):
        with pytest.raises(ValueError, match="missing_field"):
            EngineConfig(missing_field="null")

    def test_streaming_mode_honours_unknown(self):
        engine = PhreakEngine(streaming_mode=True, config=EngineConfig(missing_field="unknown"))
        engine.load_rules([_rule(NOT_BLOCKED)])
        assert engine.evaluate({"amount": 1}).fired_rules == []
        assert engine.evaluate({"amount": 1, "blocked": False}).fired_rules == [1]


class TestTristateWalk:
    def _eval(self, node, facts):
        return evaluate_tristate(
            node.to_dict() if hasattr(node, "to_dict") else node,
            facts,
            leaf=lambda n, f: f[n["field"]] == n["value"],
            other=lambda n, f: False,
            empty=True,
        )

    def test_missing_leaf_is_unknown(self):
        assert self._eval({"type": "condition", "field": "x", "op": "==", "value": 1}, {}) is None

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "and", "conditions": []}, True),
            ({"type": "or", "conditions": []}, False),
            ({"type": "not"}, True),
            ({"type": "exists", "field": "x"}, False),
        ],
    )
    def test_degenerate_nodes(self, node, expected):
        assert self._eval(node, {}) is expected

    def test_leaf_fields_skip_exists(self):
        node = {
            "type": "and",
            "conditions": [
                {"type": "exists", "field": "e"},
                {"type": "condition", "field": "a", "op": "==", "value": 1},
                {
                    "type": "not",
                    "condition": {"type": "condition", "field": "b", "op": "==", "value": 1},
                },
            ],
        }
        assert leaf_fields(node) == ("a", "b")
