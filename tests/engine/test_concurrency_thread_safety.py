"""Concurrency & thread-safety tests for stateless PhreakEngine evaluation (P0.2).

These tests pin down the concurrency contract from the trust-hardening plan
(``.research/PHREAK_P0_PLAN_TRUST_FOUNDATION.md``, task P0.2):

- A single stateless ``PhreakEngine`` instance may be evaluated concurrently
  from many threads and MUST return, for every fact, the exact fired-rule set a
  serial run would produce (no shared-state races).
- ``BitMaskLinker.linked_rules_for`` is a pure, side-effect-free query: it never
  mutates linker state and agrees with the mutating ``update_facts`` path.
- Stateless ``evaluate()`` mutates no shared instance attribute (the per-cycle
  leaf memo is thread-local; the linker is queried, not mutated).
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

from fluxrules import Rule
from fluxrules.engine.infrastructure.bitmask_linker import BitMaskLinker
from fluxrules.engine.phreak import PhreakEngine


def _rule(rid: int, field: str, op: str = ">", value: int = 100) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        priority=rid % 10,
        domain=f"d{rid % 5}",
        tags=frozenset(),
        persist=False,
    )


def _diverse_rules(n: int, n_fields: int = 20) -> list[Rule]:
    return [_rule(i, field=f"field_{i % n_fields}", value=(i * 7) % 1000) for i in range(n)]


def _random_fact(n_fields: int = 20, rng: random.Random | None = None) -> dict:
    rng = rng or random
    # Include a random subset of fields with random values so both linkage
    # (presence) and condition evaluation (value) vary across facts.
    k = rng.randint(1, 4)
    return {f"field_{rng.randint(0, n_fields - 1)}": rng.randint(0, 1000) for _ in range(k)}


class TestLinkedRulesForParity:
    """`linked_rules_for` must equal the mutating update_facts path, no writes."""

    def test_parity_with_update_facts(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_segment("seg_AB", frozenset(["field_A", "field_B"]))
        linker.register_rule(1, ["seg_A"])
        linker.register_rule(2, ["seg_AB"])

        for present in [
            set(),
            {"field_A"},
            {"field_B"},
            {"field_A", "field_B"},
            {"field_A", "field_C"},
        ]:
            fact = dict.fromkeys(present, 1)
            # Mutating path (ground truth).
            linker.update_facts(fact)
            expected = linker.get_linked_rules()
            # Pure path.
            actual = linker.linked_rules_for(frozenset(present))
            assert actual == expected, f"presence={present}: {actual} != {expected}"

    def test_does_not_mutate_state(self):
        linker = BitMaskLinker()
        linker.register_segment("seg_A", frozenset(["field_A"]))
        linker.register_rule(1, ["seg_A"])

        # Snapshot mutable state before the pure query.
        before_global = linker._global_state
        before_linked = set(linker._linked_rules)
        before_present = set(linker._present_fields)

        _ = linker.linked_rules_for(frozenset({"field_A"}))

        assert linker._global_state == before_global
        assert linker._linked_rules == before_linked
        assert linker._present_fields == before_present

    def test_empty_field_segment_is_always_linked(self):
        """A segment with no fields must be active (parity with update_facts)."""
        linker = BitMaskLinker()
        linker.register_segment("seg_empty", frozenset())
        linker.register_rule(9, ["seg_empty"])

        linker.update_facts({"anything": 1})
        expected = linker.get_linked_rules()
        assert linker.linked_rules_for(frozenset({"anything"})) == expected


class TestStatelessSharedInstanceThreadSafety:
    """One shared stateless engine, hammered from many threads == serial result."""

    def test_concurrent_eval_matches_serial(self):
        rng = random.Random(1234)
        n_fields = 20
        rules = _diverse_rules(2000, n_fields=n_fields)

        engine = PhreakEngine(streaming_mode=False)
        engine.load_rules(rules)

        facts = [_random_fact(n_fields, rng) for _ in range(2000)]

        # Golden serial result computed on a SEPARATE engine instance so the
        # concurrent run cannot be contaminated by it.
        golden_engine = PhreakEngine(streaming_mode=False)
        golden_engine.load_rules(rules)
        expected = [frozenset(golden_engine.evaluate(f).fired_rules) for f in facts]

        # Concurrent run on a single shared engine instance.
        def _eval(i: int) -> tuple[int, frozenset]:
            return i, frozenset(engine.evaluate(facts[i]).fired_rules)

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(_eval, range(len(facts))))

        for i, got in results:
            assert got == expected[i], (
                f"fact #{i} {facts[i]}: concurrent {sorted(got)} != serial {sorted(expected[i])}"
            )

    def test_stateless_eval_does_not_mutate_linker_state(self):
        """Stateless evaluate() must not write the linker's mutable fields."""
        rules = _diverse_rules(500)
        engine = PhreakEngine(streaming_mode=False)
        engine.load_rules(rules)

        linker = engine._bitmask_linker
        before_global = linker._global_state
        before_linked = set(linker._linked_rules)

        for _ in range(50):
            engine.evaluate(_random_fact())

        assert linker._global_state == before_global
        assert linker._linked_rules == before_linked

    def test_leaf_memo_is_thread_local(self):
        """Each thread sees its own per-cycle leaf memo (no cross-thread sharing)."""
        rules = _diverse_rules(200)
        engine = PhreakEngine(streaming_mode=False)
        engine.load_rules(rules)

        seen: list = []

        def _worker(_i: int) -> None:
            engine.evaluate({"field_0": 999})
            # After a sequential cycle the memo dict belongs to THIS thread.
            seen.append(id(engine._thread_local.__dict__.get("leaf_memo")))

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_worker, range(4)))

        # Distinct per-thread memo objects (no single shared dict across threads).
        assert len(set(seen)) >= 2
