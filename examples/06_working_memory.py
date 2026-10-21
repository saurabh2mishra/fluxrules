"""Batch 2 example: working memory with assert_fact and retract_fact.

``PhreakEngine`` keeps a working memory of facts you assert. Each asserted fact
gets an id you can retract later, and ``get_stats()["facts_in_memory"]`` reports
how many are held.

``evaluate()`` is still a pure call on the fact you pass in: stored facts do not
change its answer. Use working memory to hold the facts of a session, and
retract them when they stop applying. For an engine that remembers the previous
evaluation, see 20_streaming_mode.py.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("06_working_memory.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    engine.load_rules(build_shared_rules())

    print("\nAssert every transaction into working memory:")
    handles: dict[str, str] = {}
    for fact in SHARED_FACTS:
        handles[fact["fact_id"]] = engine.assert_fact(fact)
        print(
            f"  asserted {fact['fact_id']} -> "
            f"facts in memory = {engine.get_stats()['facts_in_memory']}"
        )

    print("\nEvaluate each stored transaction:")
    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"  {fact['fact_id']}: matched={result.fired_rules} actions={result.actions}")

    print("\nRetract txn-003 once it has been settled:")
    engine.retract_fact(handles["txn-003"])
    print(f"  facts in memory = {engine.get_stats()['facts_in_memory']}")

    # Working memory does not feed evaluate(): an empty fact still matches
    # nothing, even with two transactions stored.
    result = engine.evaluate({})
    print(f"\nevaluate({{}}) with 2 facts stored -> matched={result.fired_rules}")


if __name__ == "__main__":
    main()
