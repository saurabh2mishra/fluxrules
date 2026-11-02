"""engine.evaluate_batch(): full results, in input order, with every engine option.

``workers=None`` / ``1`` loops ``evaluate`` in this process. ``workers > 1``
rebuilds the engine from its settings in worker processes. Both must give the
same results as a plain loop over ``evaluate``.

Models and pipeline functions used with workers are defined at module level:
worker processes receive them by pickling, which needs an importable name.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from fluxrules import F, Rule
from fluxrules.domain.errors import FactValidationError, FieldNotFoundError
from fluxrules.domain.models import EvaluationResult
from fluxrules.engine.base import BaseEngine
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import FactPipeline
from fluxrules.pipeline.transforms import Filter


class Payment(BaseModel):
    amount: float
    country: str = "US"
    blocked: bool | None = None


def add_country(fact: dict[str, Any]) -> dict[str, Any]:
    return {"country": "DE", **fact}


RULES = [
    Rule(id=1, name="big", conditions=F("amount") > 1000, action="review", tags=["risk"]),
    Rule(id=2, name="german", conditions=F("country") == "DE", action="vat", domain="tax"),
    Rule(id=3, name="not_blocked", conditions=~(F("blocked") == True), action="allow"),  # noqa: E712
]

FACTS = [
    {"amount": 5000, "country": "DE", "blocked": False},
    {"amount": 10, "country": "US", "blocked": True},
    {"amount": 2000, "country": "FR", "blocked": False},
    {"amount": 1, "country": "DE", "blocked": False},
    {"amount": 999, "country": "US", "blocked": False},
]

_COMPARED = (
    "fired_rules",
    "actions",
    "rules_by_domain",
    "rules_by_tag",
    "explanations",
    "candidate_rule_ids",
)


def _view(result: EvaluationResult) -> dict[str, Any]:
    return {name: getattr(result, name) for name in _COMPARED}


def _engine(**kwargs: Any) -> PhreakEngine:
    kwargs.setdefault("config", EngineConfig(missing_field="false"))
    engine = PhreakEngine(**kwargs)
    engine.load_rules(RULES)
    return engine


class TestInProcess:
    @pytest.mark.parametrize("workers", [None, 1])
    def test_matches_a_loop_over_evaluate(self, workers: int | None) -> None:
        engine = _engine()
        expected = [_view(engine.evaluate(fact)) for fact in FACTS]
        got = engine.evaluate_batch(FACTS, workers=workers)
        assert all(isinstance(r, EvaluationResult) for r in got)
        assert [_view(r) for r in got] == expected

    def test_accepts_any_iterable(self) -> None:
        engine = _engine()
        got = engine.evaluate_batch(fact for fact in FACTS)
        assert len(got) == len(FACTS)

    def test_empty_input(self) -> None:
        assert _engine().evaluate_batch([]) == []
        assert _engine().evaluate_batch([], workers=2) == []

    @pytest.mark.parametrize("workers", [0, -1, True, 1.5, "2"])
    def test_bad_workers(self, workers: Any) -> None:
        with pytest.raises(ValueError, match="workers must be None or a positive integer"):
            _engine().evaluate_batch(FACTS, workers=workers)

    def test_streaming_mode_works_in_process(self) -> None:
        engine = _engine(streaming_mode=True)
        # The same fact twice: streaming skips the unchanged repeat.
        results = engine.evaluate_batch([FACTS[0], FACTS[0]])
        assert results[0].fired_rules
        assert results[1].fired_rules == []


class TestWorkers:
    @pytest.mark.parametrize("workers", [2, 4])
    def test_same_results_in_order(self, workers: int) -> None:
        engine = _engine()
        expected = [_view(r) for r in engine.evaluate_batch(FACTS)]
        got = engine.evaluate_batch(FACTS, workers=workers)
        assert [_view(r) for r in got] == expected

    def test_workers_capped_to_fact_count(self) -> None:
        engine = _engine()
        got = engine.evaluate_batch(FACTS[:2], workers=16)
        assert [r.fired_rules for r in got] == [engine.evaluate(f).fired_rules for f in FACTS[:2]]

    def test_compiled_conditions_apply(self) -> None:
        engine = _engine(compile_conditions=True)
        expected = [_view(engine.evaluate(f)) for f in FACTS]
        assert [_view(r) for r in engine.evaluate_batch(FACTS, workers=2)] == expected

    def test_validate_facts_normalizes_in_workers(self) -> None:
        engine = _engine(fact_schema=Payment, validate_facts="normalize")
        facts = [{"amount": "4200"}, {"amount": "5"}]
        got = engine.evaluate_batch(facts, workers=2)
        # "4200" is coerced to 4200.0, so rule 1 fires; a raw string would not.
        assert 1 in got[0].fired_rules
        assert 1 not in got[1].fired_rules

    def test_fact_pipeline_applies_in_workers(self) -> None:
        engine = _engine(fact_pipeline=add_country)
        got = engine.evaluate_batch([{"amount": 1}, {"amount": 2}], workers=2)
        assert all(2 in r.fired_rules for r in got)

    def test_missing_field_config_applies_in_workers(self) -> None:
        facts = [{"amount": 1}, {"amount": 2}]  # no "blocked" key
        old = _engine(config=EngineConfig(missing_field="false"))
        new = _engine(config=EngineConfig(missing_field="unknown"))
        assert all(3 in r.fired_rules for r in old.evaluate_batch(facts, workers=2))
        assert all(3 not in r.fired_rules for r in new.evaluate_batch(facts, workers=2))

    def test_model_instances_as_input(self) -> None:
        engine = _engine(fact_schema=Payment)
        facts = [Payment(amount=5000, country="DE"), Payment(amount=1)]
        expected = [_view(engine.evaluate(f)) for f in facts]
        assert [_view(r) for r in engine.evaluate_batch(facts, workers=2)] == expected

    def test_metrics_record_worker_results(self) -> None:
        engine = _engine(enable_metrics=True)
        engine.evaluate_batch(FACTS, workers=2)
        assert engine.get_observability_metrics()["eval_latency_samples"] == len(FACTS)


class TestInvalidFacts:
    FACTS = [{"amount": 5000}, {"amount": "x"}, {"amount": 1}, {"amount": "y"}]

    def test_quarantine_is_gathered_in_input_order(self) -> None:
        engine = _engine(fact_schema=Payment, validate_facts="normalize", on_invalid="quarantine")
        got = engine.evaluate_batch(self.FACTS, workers=2)
        assert [r.fired_rules for r in got][1] == []
        assert [r.fired_rules for r in got][3] == []
        assert [q.facts for q in engine.quarantined_facts] == [{"amount": "x"}, {"amount": "y"}]
        assert all(isinstance(q.error, FactValidationError) for q in engine.quarantined_facts)

    def test_quarantine_matches_in_process(self) -> None:
        single = _engine(fact_schema=Payment, validate_facts="normalize", on_invalid="quarantine")
        multi = _engine(fact_schema=Payment, validate_facts="normalize", on_invalid="quarantine")
        single.evaluate_batch(self.FACTS)
        multi.evaluate_batch(self.FACTS, workers=4)
        assert [q.facts for q in multi.quarantined_facts] == [
            q.facts for q in single.quarantined_facts
        ]

    @pytest.mark.parametrize("workers", [1, 2, 4])
    def test_raise_reports_the_first_invalid_fact(self, workers: int) -> None:
        engine = _engine(fact_schema=Payment, validate_facts="normalize", on_invalid="raise")
        with pytest.raises(FactValidationError) as info:
            engine.evaluate_batch(self.FACTS, workers=workers)
        assert info.value.schema_name == "Payment"
        assert info.value.errors[0]["input"] == "x"

    def test_other_errors_propagate_from_workers(self) -> None:
        engine = _engine()
        facts = [{"amount": 1, "country": "US", "blocked": False}, {"Amount": 1}]
        with pytest.raises(FieldNotFoundError):
            engine.evaluate_batch(facts, workers=2)

    def test_dropped_facts_get_empty_results(self) -> None:
        pipeline = FactPipeline([Filter(_has_amount)])
        engine = _engine(fact_pipeline=pipeline)
        got = engine.evaluate_batch([{"amount": 5000}, {"country": "DE"}], workers=2)
        assert 1 in got[0].fired_rules
        assert got[1].fired_rules == []


def _has_amount(fact: dict[str, Any]) -> bool:
    return "amount" in fact


class TestCannotUseWorkers:
    def test_lambda_in_pipeline_is_a_clear_error(self) -> None:
        engine = _engine(fact_pipeline=FactPipeline([Filter(lambda f: True)]))
        with pytest.raises(ValueError, match="fact_pipeline could not be pickled"):
            engine.evaluate_batch(FACTS, workers=2)
        # In process it still works.
        assert len(engine.evaluate_batch(FACTS)) == len(FACTS)

    def test_local_schema_is_a_clear_error(self) -> None:
        class Local(Payment):
            pass

        engine = _engine(fact_schema=Local, validate_facts="normalize")
        with pytest.raises(ValueError, match="fact_schema could not be pickled"):
            engine.evaluate_batch([{"amount": 1}, {"amount": 2}], workers=2)

    def test_checks_run_even_for_one_fact(self) -> None:
        engine = _engine(fact_pipeline=lambda f: f)
        with pytest.raises(ValueError, match="could not be pickled"):
            engine.evaluate_batch(FACTS[:1], workers=2)

    def test_streaming_mode_with_workers(self) -> None:
        engine = _engine(streaming_mode=True)
        with pytest.raises(ValueError, match="streaming_mode"):
            engine.evaluate_batch(FACTS, workers=2)

    def test_custom_base_engine(self) -> None:
        engine = _AllRulesEngine()
        engine.load_rules(RULES)
        assert len(engine.evaluate_batch(FACTS)) == len(FACTS)
        with pytest.raises(NotImplementedError, match="workers=1"):
            engine.evaluate_batch(FACTS, workers=2)

    def test_phreak_subclass_with_own_init(self) -> None:
        engine = _TunedEngine(label="x")
        engine.load_rules(RULES)
        with pytest.raises(NotImplementedError, match="own __init__"):
            engine.evaluate_batch(FACTS, workers=2)


class _AllRulesEngine(BaseEngine):
    def _evaluate_rules(self, candidate_rule_ids, facts):  # type: ignore[no-untyped-def]
        return [], [], {}


class _TunedEngine(PhreakEngine):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label


def test_pickling_a_fact_validation_error_keeps_its_fields() -> None:
    import pickle

    error = FactValidationError("Payment", [{"loc": ("amount",), "msg": "bad"}])
    copy = pickle.loads(pickle.dumps(error))
    assert (copy.schema_name, copy.errors, str(copy)) == (
        error.schema_name,
        error.errors,
        str(error),
    )


class NeedsKeyword(Exception):
    """An exception pickle cannot rebuild (its __init__ needs a keyword)."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)


class _RaisingEngine(PhreakEngine):
    def evaluate(self, facts, filters=None, *, strict_facts=False):  # type: ignore[no-untyped-def]
        raise NeedsKeyword(reason="boom")


class TestReviewFixes:
    def test_in_process_keeps_the_original_exception(self) -> None:
        from fluxrules.engine.runtime.worker_pool import run_sharded

        outcome = run_sharded(_RaisingEngine, {}, RULES, FACTS, 1)
        assert type(outcome.error) is NeedsKeyword

    def test_worker_turns_an_unpicklable_exception_into_runtime_error(self) -> None:
        from fluxrules.engine.runtime.worker_pool import run_sharded

        outcome = run_sharded(_RaisingEngine, {}, RULES, FACTS, 2)
        assert isinstance(outcome.error, RuntimeError)
        assert "NeedsKeyword: boom" in str(outcome.error)

    def test_unpicklable_engine_class_is_a_clear_error(self) -> None:
        class LocalEngine(PhreakEngine):
            pass

        engine = LocalEngine()
        engine.load_rules(RULES)
        with pytest.raises(ValueError, match="the engine class could not be pickled"):
            engine.evaluate_batch(FACTS, workers=2)

    def test_payload_is_pickled_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pickle

        from fluxrules.engine.runtime import worker_pool

        dumps = []

        class _CountingPickle:
            loads = staticmethod(pickle.loads)

            @staticmethod
            def dumps(obj, *args, **kwargs):  # type: ignore[no-untyped-def]
                dumps.append(type(obj).__name__)
                return pickle.dumps(obj, *args, **kwargs)

        monkeypatch.setattr(worker_pool, "pickle", _CountingPickle)
        _engine().evaluate_batch(FACTS, workers=2)
        assert dumps == ["tuple"]  # one payload; nothing pickled again per worker


class _CountingEngine(BaseEngine):
    """A custom engine that opts in to workers, as docs/custom-engines.md shows."""

    def __init__(self, threshold: int = 0) -> None:
        super().__init__()
        self.threshold = threshold

    def _evaluate_rules(self, candidate_rule_ids, facts):  # type: ignore[no-untyped-def]
        fired = [rid for rid in candidate_rule_ids if facts.get("amount", 0) > self.threshold]
        return fired, [], {}

    def _clone_settings(self) -> tuple[type, dict[str, Any]]:
        return type(self), {"threshold": self.threshold}


def test_custom_engine_with_clone_settings_runs_in_workers() -> None:
    engine = _CountingEngine(threshold=100)
    engine.load_rules(RULES)
    expected = [engine.evaluate(f).fired_rules for f in FACTS]
    got = engine.evaluate_batch(FACTS, workers=2)
    assert [r.fired_rules for r in got] == expected
    assert any(expected) and not all(expected)


class TestWorkerCodeInProcess:
    """Code that normally runs inside worker processes, exercised here.

    Coverage does not follow worker processes, so these call the same
    functions directly in this process.
    """

    def test_payload_initializer_builds_the_engine(self) -> None:
        from fluxrules.engine.runtime import worker_pool

        engine = _engine()
        engine_class, settings = engine._clone_settings()
        payload = worker_pool.build_payload(engine_class, settings, RULES)
        try:
            worker_pool._init_worker_from_payload(payload)
            built = worker_pool._WORKER_ENGINE
            assert type(built) is PhreakEngine
            assert built.evaluate(FACTS[0]).fired_rules == engine.evaluate(FACTS[0]).fired_rules
        finally:
            worker_pool._WORKER_ENGINE = None

    def test_chunk_returns_quarantined_facts_with_their_index(self) -> None:
        from fluxrules.engine.runtime.worker_pool import run_sharded

        engine = _engine(fact_schema=Payment, validate_facts="normalize", on_invalid="quarantine")
        engine_class, settings = engine._clone_settings()
        facts = [{"amount": 1}, {"amount": "x"}, {"amount": 2}]
        outcome = run_sharded(engine_class, settings, RULES, facts, 1)
        assert [q.facts for q in outcome.quarantined] == [{"amount": "x"}]
        assert len(outcome.results) == 3

    def test_picklable_keeps_or_replaces_an_exception(self) -> None:
        from fluxrules.engine.runtime.worker_pool import _picklable

        fine = ValueError("fine")
        assert _picklable(fine) is fine
        replaced = _picklable(NeedsKeyword(reason="boom"))
        assert type(replaced) is RuntimeError
        assert str(replaced) == "NeedsKeyword: boom"

    def test_payload_error_when_only_the_whole_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pickle

        from fluxrules.engine.runtime import worker_pool

        real_dumps = pickle.dumps

        def dumps(obj, *args, **kwargs):  # type: ignore[no-untyped-def]
            if isinstance(obj, tuple):
                raise pickle.PicklingError("whole payload")
            return real_dumps(obj, *args, **kwargs)

        monkeypatch.setattr(worker_pool.pickle, "dumps", dumps)
        with pytest.raises(ValueError, match="the engine settings could not be pickled"):
            worker_pool.build_payload(PhreakEngine, {}, RULES)

    def test_evaluate_batch_parallel_raises_the_first_error(self) -> None:
        from fluxrules.engine.runtime import evaluate_batch_parallel

        with pytest.raises(FieldNotFoundError):
            evaluate_batch_parallel(RULES, [FACTS[0], {"Amount": 1}], num_workers=1)


def test_chunk_offsets() -> None:
    from fluxrules.engine.runtime.worker_pool import _chunk

    assert _chunk([1, 2, 3], 1) == [(0, [1, 2, 3])]
    assert _chunk([1], 4) == [(0, [1])]
    assert _chunk([1, 2, 3, 4, 5], 2) == [(0, [1, 2, 3]), (3, [4, 5])]
