"""Batch 4 example: the ways to evaluate a fact, side by side.

One rule set and one payment, evaluated through each way that runs inside
Python. Every way finds the same matching rules; the script checks that, then
shows what streaming mode and the result cache do differently on a repeat.

The command line (``fluxrules evaluate``) and the HTTP API use the same engine.
See docs/evaluating-facts.md for all ten ways.
"""

from __future__ import annotations

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
FACT = {"amount": 4200, "country": "DE"}
EXPECTED = [1, 2]


class Payment(BaseModel):
    amount: float
    country: str


def check(way: str, fired: list[int]) -> None:
    assert fired == EXPECTED, f"{way}: expected {EXPECTED}, got {fired}"
    print(f"  {way:44} fired {fired}")


def main() -> None:
    print("=" * 80)
    print("32_ways_to_evaluate.py")
    print(f"Fact: {FACT}")
    print("=" * 80)
    print()

    check("fluxrules.evaluate(rules, fact)", fluxrules.evaluate(RULES, FACT).fired_rules)

    engine = PhreakEngine()
    engine.load_rules(RULES)
    check("engine.evaluate(fact)", engine.evaluate(FACT).fired_rules)

    typed = PhreakEngine(fact_schema=Payment)
    typed.load_rules(RULES)
    check("engine.evaluate(Payment(...))", typed.evaluate(Payment(**FACT)).fired_rules)

    facts = [FACT, {"amount": 50, "country": "US"}, FACT]
    in_process = engine.evaluate_batch(facts)
    two_workers = engine.evaluate_batch(facts, workers=2)
    assert [r.fired_rules for r in in_process] == [r.fired_rules for r in two_workers]
    check("engine.evaluate_batch(facts)", in_process[0].fired_rules)
    check("engine.evaluate_batch(facts, workers=2)", two_workers[0].fired_rules)

    stream = PhreakEngine(streaming_mode=True)
    stream.load_rules(RULES)
    check("streaming engine, first time", stream.evaluate(FACT).fired_rules)

    dedup = DedupEvaluator(engine)
    check("DedupEvaluator, first time", dedup.evaluate(FACT).fired_rules)

    service = RuleService.create()
    service.persist(
        Ruleset(group="payments", rules=tuple(r.to_engine_rule(group="payments") for r in RULES))
    )
    session = service.create_session("payments")
    session.add_fact("amount", FACT["amount"])
    session.add_fact("country", FACT["country"])
    check("session.evaluate()", session.evaluate().fired_rules)

    print("\nThe same fact sent a second time:\n")
    repeat = stream.evaluate(FACT).fired_rules
    print(f"  streaming engine: fired {repeat} (an unchanged fact is skipped)")
    assert repeat == []
    cached = dedup.evaluate(FACT).fired_rules
    print(f"  DedupEvaluator:   fired {cached} (answer taken from the cache)")
    assert cached == EXPECTED and dedup.stats.hits == 1


if __name__ == "__main__":
    # Required: evaluate_batch(workers=2) starts processes, which import this
    # script again on macOS and Windows.
    main()
