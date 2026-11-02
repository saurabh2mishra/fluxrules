"""Every way to evaluate a fact finds the same matching rules.

docs/evaluating-facts.md promises that the evaluation paths share one rule
set and one matching logic, so the same fact always matches the same rules.
This file checks that promise across the paths that run in-process, plus the
documented differences of streaming mode and the result cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

import fluxrules
from fluxrules import F, Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import DedupEvaluator
from fluxrules.services.rule_service import RuleService

RULES = [
    Rule(id=1, name="big_payment", conditions=F("amount") > 1000, action="review", priority=10),
    Rule(id=2, name="german_payment", conditions=F("country") == "DE", action="add_vat"),
]

FACTS = [
    {"amount": 4200, "country": "DE"},
    {"amount": 50, "country": "US"},
    {"amount": 9000, "country": "FR"},
    {"amount": 10, "country": "DE"},
]


class Payment(BaseModel):
    amount: float
    country: str


def _engine(**kwargs) -> PhreakEngine:  # type: ignore[no-untyped-def]
    engine = PhreakEngine(**kwargs)
    engine.load_rules(RULES)
    return engine


@pytest.fixture(scope="module")
def expected() -> list[list[int]]:
    engine = _engine()
    return [engine.evaluate(fact).fired_rules for fact in FACTS]


def test_expected_answers_are_not_trivial(expected: list[list[int]]) -> None:
    assert expected == [[1, 2], [], [1], [2]]


def test_top_level_evaluate(expected: list[list[int]]) -> None:
    assert [fluxrules.evaluate(RULES, fact).fired_rules for fact in FACTS] == expected


def test_model_instances(expected: list[list[int]]) -> None:
    engine = _engine(fact_schema=Payment)
    assert [engine.evaluate(Payment(**fact)).fired_rules for fact in FACTS] == expected


def test_compiled_conditions(expected: list[list[int]]) -> None:
    engine = _engine(compile_conditions=True)
    assert [engine.evaluate(fact).fired_rules for fact in FACTS] == expected


@pytest.mark.parametrize("workers", [None, 1, 2])
def test_evaluate_batch(expected: list[list[int]], workers: int | None) -> None:
    results = _engine().evaluate_batch(FACTS, workers=workers)
    assert [r.fired_rules for r in results] == expected


def test_dedup_evaluator(expected: list[list[int]]) -> None:
    dedup = DedupEvaluator(_engine())
    first = [dedup.evaluate(fact).fired_rules for fact in FACTS]
    again = [dedup.evaluate(dict(reversed(fact.items()))).fired_rules for fact in FACTS]
    assert first == again == expected
    assert (dedup.stats.misses, dedup.stats.hits) == (len(FACTS), len(FACTS))


def test_stored_rule_set_and_session(expected: list[list[int]]) -> None:
    service = RuleService.create()
    service.persist(
        Ruleset(group="payments", rules=tuple(r.to_engine_rule(group="payments") for r in RULES))
    )
    assert [service.evaluate_ruleset("payments", f).fired_rules for f in FACTS] == expected

    fired = []
    for fact in FACTS:
        session = service.create_session("payments")
        for key, value in fact.items():
            session.add_fact(key, value)
        fired.append(session.evaluate().fired_rules)
    assert fired == expected


def test_cli(expected: list[list[int]], tmp_path: Path) -> None:
    pytest.importorskip("typer")
    from typer.testing import CliRunner

    from fluxrules.cli.main import app

    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps([r.model_dump(mode="json") for r in RULES]))
    for fact, want in zip(FACTS, expected, strict=True):
        event = tmp_path / "event.json"
        event.write_text(json.dumps(fact))
        out = CliRunner().invoke(app, ["evaluate", str(rules_file), str(event), "--format", "json"])
        assert out.exit_code == 0, out.output
        assert [rule["id"] for rule in json.loads(out.output)["matched_rules"]] == want


class TestStreamingMode:
    def test_first_sight_matches_stateless(self, expected: list[list[int]]) -> None:
        engine = _engine(streaming_mode=True)
        assert [engine.evaluate(fact).fired_rules for fact in FACTS] == expected

    def test_unchanged_repeat_is_skipped(self) -> None:
        engine = _engine(streaming_mode=True)
        assert engine.evaluate(FACTS[0]).fired_rules == [1, 2]
        assert engine.evaluate(FACTS[0]).fired_rules == []

    def test_changed_fact_is_evaluated_again(self) -> None:
        engine = _engine(streaming_mode=True)
        engine.evaluate(FACTS[0])
        assert engine.evaluate({**FACTS[0], "amount": 10}).fired_rules == [2]
