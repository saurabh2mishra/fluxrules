"""Tests for RuleEnginePool and the build-once adapter path (P0.1).

Acceptance criteria from ``.research/PHREAK_P0_PLAN_TRUST_FOUNDATION.md`` (P0.1):

- An unchanged rule set is built (``load_rules``) exactly once and reused.
- A changed rule set triggers exactly one rebuild.
- Concurrent callers during a (re)build never observe a half-built engine.
- The API adapter no longer calls ``load_rules`` per request.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fluxrules.api.engines.engine_pool import RuleEnginePool, rules_signature


def _rule(rid: int, field: str = "amount", op: str = ">", value: int = 100) -> dict:
    return {
        "id": rid,
        "name": f"rule_{rid}",
        "condition_dsl": {
            "type": "condition",
            "field": field,
            "op": op,
            "value": value,
        },
        "priority": rid % 10,
        "tags": [f"tag_{rid % 3}"],
        "group": f"g{rid % 2}",
    }


def _rules(n: int) -> list[dict]:
    return [_rule(i, field=f"field_{i % 10}", value=i) for i in range(n)]


class TestRulesSignature:
    def test_order_independent(self):
        rules = _rules(20)
        assert rules_signature(rules) == rules_signature(list(reversed(rules)))

    def test_changes_on_condition_change(self):
        a = _rules(5)
        b = _rules(5)
        b[2]["condition_dsl"]["value"] = 999_999
        assert rules_signature(a) != rules_signature(b)

    def test_changes_on_rule_added(self):
        a = _rules(5)
        b = _rules(6)
        assert rules_signature(a) != rules_signature(b)


class TestRuleEnginePoolBuildOnce:
    def test_same_rules_build_once(self):
        pool = RuleEnginePool(engine_type="PHREAK")
        rules = _rules(50)

        first = pool.get(rules)
        for _ in range(25):
            again = pool.get(rules)
            assert again is first  # exact same engine object reused

        assert pool.stats["builds"] == 1
        assert pool.stats["hits"] == 25

    def test_changed_rules_rebuild_once(self):
        pool = RuleEnginePool(engine_type="PHREAK")
        rules_v1 = _rules(50)
        rules_v2 = _rules(50)
        rules_v2[0]["condition_dsl"]["value"] = 123456  # change → new signature

        e1 = pool.get(rules_v1)
        e2 = pool.get(rules_v2)
        assert e1 is not e2
        assert pool.stats["builds"] == 2

        # Going back to v1 reuses the still-warm engine (no rebuild).
        assert pool.get(rules_v1) is e1
        assert pool.stats["builds"] == 2

    def test_lru_eviction_bounds_memory(self):
        pool = RuleEnginePool(engine_type="PHREAK", max_instances=2)
        # Three distinct rule sets, cap of 2 → at most 2 warm engines.
        for v in range(3):
            rules = _rules(10)
            rules[0]["condition_dsl"]["value"] = v
            pool.get(rules)
        assert pool.stats["warm_engines"] == 2

    def test_invalidate_forces_rebuild(self):
        pool = RuleEnginePool(engine_type="PHREAK")
        rules = _rules(30)
        e1 = pool.get(rules)
        pool.invalidate()
        e2 = pool.get(rules)
        assert e1 is not e2
        assert pool.stats["builds"] == 2

    def test_evaluation_results_match_direct_engine(self):
        """Held engine must produce the same fired rules as a directly-loaded one."""
        from fluxrules.engine.phreak import PhreakEngine

        rules = _rules(100)
        pool = RuleEnginePool(engine_type="PHREAK")
        held = pool.get(rules)

        direct = PhreakEngine()
        direct.load_rules(rules)

        for fact in [{"field_0": 999}, {"field_3": 0}, {"field_7": 500}, {"x": 1}]:
            assert set(held.evaluate(fact).fired_rules) == set(direct.evaluate(fact).fired_rules)


class TestRuleEnginePoolConcurrency:
    def test_concurrent_first_build_is_single_and_safe(self):
        """Many threads racing the very first get() build exactly one engine."""
        pool = RuleEnginePool(engine_type="PHREAK")
        rules = _rules(200)

        def _get(_i: int):
            return pool.get(rules)

        with ThreadPoolExecutor(max_workers=8) as ex:
            engines = list(ex.map(_get, range(64)))

        # All callers received the same fully-built engine; only one build paid.
        assert all(e is engines[0] for e in engines)
        assert pool.stats["builds"] == 1

    def test_concurrent_eval_on_held_engine_matches_serial(self):
        """The held engine is safe to evaluate concurrently (relies on P0.2)."""
        pool = RuleEnginePool(engine_type="PHREAK")
        rules = _rules(500)
        engine = pool.get(rules)

        facts = [{f"field_{i % 10}": i} for i in range(500)]
        expected = [frozenset(engine.evaluate(f).fired_rules) for f in facts]

        def _eval(i: int):
            return i, frozenset(engine.evaluate(facts[i]).fired_rules)

        with ThreadPoolExecutor(max_workers=8) as ex:
            for i, got in ex.map(_eval, range(len(facts))):
                assert got == expected[i]
