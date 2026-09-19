"""P1.1 - Adaptive alpha engage decision.

The old engine throttled the alpha pre-filter behind a hardcoded
``len(matched_rule_ids) >= 64`` gate, making the load-bearing value-aware
optimization secondary. P1.1 replaces that with an adaptive, selectivity-driven
decision computed once at load time (``PhreakEngine._compute_alpha_engage``):

- A rule set that *can* prune (has at least one filterable signature) ⇒ alpha
  engages and the prune ratio is > 0 on selective facts.
- A degenerate rule set where every rule is unfilterable (e.g. all ``NOT`` /
  custom predicates) ⇒ alpha is bypassed: the scan could only ever return the
  full universe, so engaging would be pure overhead.

Gate doc: ``.research/PHREAK_P1_PLAN_SCALING_EFFICIENCY.md`` task P1.1
(``test_alpha_adaptive_gate.py``).
"""

from __future__ import annotations

from fluxrules import Rule
from fluxrules.engine.phreak._engine import PhreakEngine


def _leaf(field: str, op: str, value) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


def test_no_magic_64_attribute_remains() -> None:
    """The hardcoded ``>= 64`` gate attribute must be gone (replaced by adaptive)."""
    engine = PhreakEngine()
    assert not hasattr(engine, "_alpha_prefilter_min_rules"), (
        "static rule-count gate should be replaced by the adaptive decision"
    )


def test_high_sharing_set_engages_and_prunes() -> None:
    """Many rules sharing few signatures ⇒ alpha engages, prune ratio > 0."""
    # 500 rules but only a handful of distinct necessary-condition signatures
    # (high condition sharing) - the cheap-scan / high-payoff case.
    rules = []
    thresholds = [10, 20, 30, 40, 50]
    for i in range(500):
        t = thresholds[i % len(thresholds)]
        rules.append(Rule(id=i, name=f"r{i}", condition_dsl=_leaf("score", ">", t), persist=False))

    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    assert engine._alpha_engage is True
    assert engine._alpha_index is not None
    # Only 5 distinct signatures despite 500 rules - cheap scan.
    assert engine._alpha_index.signature_count == len(thresholds)

    # A selective fact fires only the rules with threshold < 15 ⇒ {10}.
    engine.evaluate({"score": 15})
    stats = engine.get_prefilter_stats()
    assert stats["engaged"] is True
    assert stats["prune_ratio"] > 0.0
    assert stats["last_candidates_out"] < stats["last_candidates_in"]


def test_all_unfilterable_set_bypasses_alpha() -> None:
    """Every rule unfilterable (NOT) ⇒ alpha bypassed, no wasted scan."""
    rules = [
        Rule(
            id=i,
            name=f"r{i}",
            condition_dsl={"type": "not", "condition": _leaf("f", "==", i)},
            persist=False,
        )
        for i in range(50)
    ]
    engine = PhreakEngine(alpha_prefilter=True)
    engine.load_rules(rules)

    # Index is pass-through with no filterable signatures ⇒ cannot prune.
    assert engine._alpha_index is not None
    assert engine._alpha_index.can_prune is False
    assert engine._alpha_engage is False

    engine.evaluate({"f": 999})
    stats = engine.get_prefilter_stats()
    # Alpha never engaged: every fact went straight to the linker narrow.
    assert stats["engaged"] is False
    assert stats["engaged_facts"] == 0
    assert stats["bypassed_facts"] >= 1
    # Bypassed ⇒ candidates pass through the alpha layer unchanged.
    assert stats["candidates_in"] == stats["candidates_out"]


def test_alpha_disabled_flag_never_engages() -> None:
    """``alpha_prefilter=False`` keeps the A/B switch fully off (P1.1 step 5)."""
    rules = [
        Rule(id=i, name=f"r{i}", condition_dsl=_leaf("x", ">", i), persist=False)
        for i in range(100)
    ]
    engine = PhreakEngine(alpha_prefilter=False)
    engine.load_rules(rules)

    assert engine._alpha_index is None
    assert engine._alpha_engage is False
    engine.evaluate({"x": 5})
    stats = engine.get_prefilter_stats()
    assert stats["enabled"] is False
    assert stats["engaged"] is False
    assert stats["engaged_facts"] == 0


def test_engage_decision_recomputed_on_reload() -> None:
    """Switching rule sets re-decides engagement and resets stats."""
    engine = PhreakEngine(alpha_prefilter=True)

    # First: filterable ⇒ engages.
    engine.load_rules(
        [
            Rule(id=i, name=f"r{i}", condition_dsl=_leaf("a", ">", i), persist=False)
            for i in range(20)
        ]
    )
    assert engine._alpha_engage is True
    engine.evaluate({"a": 5})
    assert engine.get_prefilter_stats()["facts"] == 1

    # Reload with an all-unfilterable set ⇒ bypasses, stats reset to 0 facts.
    engine.load_rules(
        [
            Rule(
                id=i,
                name=f"n{i}",
                condition_dsl={"type": "not", "condition": _leaf("a", "==", i)},
                persist=False,
            )
            for i in range(20)
        ]
    )
    assert engine._alpha_engage is False
    assert engine.get_prefilter_stats()["facts"] == 0
