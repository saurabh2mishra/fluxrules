"""Batch 3 example: streaming mode over a stream of transaction updates.

``PhreakEngine(streaming_mode=True)`` is a long-lived engine that remembers the
previous evaluation:

- a fact identical to the last one is skipped and returns no fired rules;
- a changed fact is re-evaluated and reports the rules that match it now.

That makes it a fit for an event stream where the same entity is sent again and
again and only changes matter. Because the engine holds state, one stream must
go to one engine instance. See 23_streaming_vs_stateless.py for a side-by-side
comparison.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("20_streaming_mode.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine(streaming_mode=True)
    engine.load_rules(build_shared_rules())
    print(f"\nengine mode: {engine.mode}\n")

    txn_001, txn_002, txn_003 = SHARED_FACTS
    stream = [
        ("txn-001 arrives", txn_001),
        ("txn-001 sent again, unchanged", txn_001),
        ("txn-001 again, IP risk drops to 50", {**txn_001, "ip_risk_score": 50}),
        ("txn-002 arrives", txn_002),
        ("txn-003 arrives", txn_003),
        ("txn-003 sent again, unchanged", txn_003),
    ]

    for step, (label, fact) in enumerate(stream, 1):
        result = engine.evaluate(fact)
        print(f"[{step}] {label:38} matched={result.fired_rules}")

    print("\nUnchanged repeats return [] because the engine skips work it has done.")
    print("When IP risk drops below 85, the hard-block rule 1002 stops matching.")


if __name__ == "__main__":
    main()
