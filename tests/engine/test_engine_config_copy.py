"""PhreakEngine keeps its own copy of EngineConfig.

Compiled conditions bake the condition flags in when rules load, while the
interpreter reads them on every call. If the engine shared the caller's config
object, changing it after ``load_rules`` would make the two paths disagree.
The engine therefore copies the config when it is created: later changes to
the caller's object, or to the process-wide config, never reach it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fluxrules import F, Rule
from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.phreak import PhreakEngine

RULES = [
    Rule(id=1, name="not_blocked", conditions=~(F("blocked") == True), action="allow"),  # noqa: E712
    Rule(id=2, name="not_one", conditions=F("score") != 1, action="review"),
]

# "blocked" is missing: rule 1 fires under missing_field="false", not "unknown".
# "score" is None: rule 2 fires only with strict_null_handling=True.
FACT = {"amount": 500, "score": None}


@pytest.fixture()
def restore_global_config() -> Iterator[None]:
    saved = get_config()
    yield
    set_config(saved)


def _fired(engine: PhreakEngine) -> list[int]:
    return sorted(engine.evaluate(FACT).fired_rules)


@pytest.mark.parametrize("compiled", [False, True], ids=["interpreted", "compiled"])
class TestCallerConfigChanges:
    def test_missing_field_change_after_load_is_ignored(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false")
        engine = PhreakEngine(config=config, compile_conditions=compiled)
        engine.load_rules(RULES)
        before = _fired(engine)
        assert 1 in before

        config.missing_field = "unknown"
        assert _fired(engine) == before

    def test_strict_null_change_after_load_is_ignored(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false", strict_null_handling=False)
        engine = PhreakEngine(config=config, compile_conditions=compiled)
        engine.load_rules(RULES)
        before = _fired(engine)
        assert 2 not in before

        config.strict_null_handling = True
        assert _fired(engine) == before

    def test_change_before_load_is_also_ignored(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false")
        engine = PhreakEngine(config=config, compile_conditions=compiled)
        config.missing_field = "unknown"
        engine.load_rules(RULES)
        assert 1 in _fired(engine)


def test_interpreted_and_compiled_agree_after_caller_change() -> None:
    engines = []
    for compiled in (False, True):
        config = EngineConfig(missing_field="false")
        engine = PhreakEngine(config=config, compile_conditions=compiled)
        engine.load_rules(RULES)
        config.missing_field = "unknown"
        engines.append(engine)
    assert _fired(engines[0]) == _fired(engines[1])


def test_set_config_after_creation_does_not_reach_engine(restore_global_config: None) -> None:
    set_config(EngineConfig(missing_field="false"))
    engine = PhreakEngine(compile_conditions=True)
    engine.load_rules(RULES)
    before = _fired(engine)

    get_config().missing_field = "unknown"
    set_config(EngineConfig(missing_field="unknown"))
    assert _fired(engine) == before


def test_engine_created_after_set_config_uses_new_values(restore_global_config: None) -> None:
    set_config(EngineConfig(missing_field="unknown"))
    engine = PhreakEngine()
    engine.load_rules(RULES)
    assert 1 not in _fired(engine)


def test_engine_config_is_a_copy() -> None:
    config = EngineConfig(missing_field="unknown")
    engine = PhreakEngine(config=config)
    assert engine._config is not config
    assert engine._config == config
