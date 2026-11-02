"""A config changed after load_rules reaches interpreted and compiled rules alike.

The interpreter reads ``EngineConfig`` on every call. Compiled conditions bind
the condition flags when they are built, so before this fix a change after
``load_rules`` reached interpreted rules only, and the same engine gave two
answers depending on ``compile_conditions``. The engine now recompiles when a
condition flag changes.
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


def _fired(engine: PhreakEngine) -> list[int]:
    return sorted(engine.evaluate(FACT).fired_rules)


def _engine(config: EngineConfig, compiled: bool) -> PhreakEngine:
    engine = PhreakEngine(config=config, compile_conditions=compiled)
    engine.load_rules(RULES)
    return engine


@pytest.fixture()
def restore_global_config() -> Iterator[None]:
    saved = get_config()
    yield
    set_config(saved)


@pytest.mark.parametrize("compiled", [False, True], ids=["interpreted", "compiled"])
class TestChangeAfterLoad:
    def test_missing_field(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false")
        engine = _engine(config, compiled)
        assert 1 in _fired(engine)

        config.missing_field = "unknown"
        assert 1 not in _fired(engine)

    def test_strict_null_handling(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false", strict_null_handling=False)
        engine = _engine(config, compiled)
        assert 2 not in _fired(engine)

        config.strict_null_handling = True
        assert 2 in _fired(engine)

    def test_change_back(self, compiled: bool) -> None:
        config = EngineConfig(missing_field="false")
        engine = _engine(config, compiled)
        before = _fired(engine)
        config.missing_field = "unknown"
        _fired(engine)
        config.missing_field = "false"
        assert _fired(engine) == before


def test_both_paths_agree_after_every_change() -> None:
    configs = [EngineConfig(missing_field="false") for _ in range(2)]
    engines = [_engine(configs[0], False), _engine(configs[1], True)]
    for field, value in [
        ("missing_field", "unknown"),
        ("strict_null_handling", True),
        ("missing_field", "false"),
        ("strict_null_handling", False),
    ]:
        for config in configs:
            setattr(config, field, value)
        assert _fired(engines[0]) == _fired(engines[1]), (field, value)


def test_recompiles_only_when_a_flag_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    config = EngineConfig(missing_field="false")
    engine = _engine(config, True)
    calls = []
    real = engine._compile_all_conditions
    monkeypatch.setattr(engine, "_compile_all_conditions", lambda: calls.append(1) or real())

    for _ in range(3):
        engine.evaluate(FACT)
    config.parallel_workers = 8  # not a condition flag
    engine.evaluate(FACT)
    assert calls == []

    config.missing_field = "unknown"
    engine.evaluate(FACT)
    engine.evaluate(FACT)
    assert calls == [1]


def test_mutating_the_process_wide_config_reaches_engines(
    restore_global_config: None,
) -> None:
    set_config(EngineConfig(missing_field="false"))
    engine = PhreakEngine(compile_conditions=True)
    engine.load_rules(RULES)
    assert 1 in _fired(engine)

    get_config().missing_field = "unknown"
    assert 1 not in _fired(engine)


def test_batch_workers_use_the_current_values() -> None:
    config = EngineConfig(missing_field="false")
    engine = _engine(config, True)
    config.missing_field = "unknown"
    results = engine.evaluate_batch([FACT, FACT], workers=2)
    assert all(1 not in r.fired_rules for r in results)
