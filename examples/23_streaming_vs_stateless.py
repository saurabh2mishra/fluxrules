"""Batch 4 example: stateless and streaming mode, side by side.

The same stream of facts goes to two engines:

- **stateless** (the default) answers every call in full, so any instance can
  serve any request behind a load balancer;
- **streaming** remembers the previous call and skips an unchanged fact, so one
  stream must always go to the same instance (sticky routing).

Pick stateless unless you own a long-lived stream and want only changes.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine


def main() -> None:
    print("=" * 80)
    print("23_streaming_vs_stateless.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    stateless = PhreakEngine()
    streaming = PhreakEngine(streaming_mode=True)
    for engine in (stateless, streaming):
        engine.load_rules(build_shared_rules())

    txn_001, txn_002, _ = SHARED_FACTS
    stream = [
        ("txn-001", txn_001),
        ("txn-001 (repeat)", txn_001),
        ("txn-001 (repeat)", txn_001),
        ("txn-002", txn_002),
        ("txn-002 (repeat)", txn_002),
    ]

    print(f"\n{'fact':20} {'stateless':22} {'streaming':22}")
    for label, fact in stream:
        a = stateless.evaluate(fact).fired_rules
        b = streaming.evaluate(fact).fired_rules
        print(f"{label:20} {a!s:22} {b!s:22}")

    print("\nStateless repeats the full answer; streaming reports nothing for repeats.")


if __name__ == "__main__":
    main()
