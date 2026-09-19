"""Batch 2 example: the pluggable engine registry over the shared use case.

FluxRules ships a single production engine (PHREAK) but exposes it through a
pluggable registry so callers select an engine by name and custom engines can be
registered under the same contract. This example demonstrates:

* discovering the available engines with ``get_available_engines``;
* instantiating the engine by name with ``get_engine``;
* running the same ruleset in stateless and streaming evaluation modes.
"""

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine import get_available_engines, get_engine


def main() -> None:
    print("=" * 80)
    print("10_pluggable_engines.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    rules = build_shared_rules()

    print(f"\nAvailable engines: {get_available_engines()}")

    print("\n--- Engine via registry (stateless) ---")
    stateless = get_engine("PHREAK")
    stateless.load_rules(rules)
    for fact in SHARED_FACTS:
        result = stateless.evaluate(fact)
        print(f"fact={fact['fact_id']} matched={result.fired_rules}")

    print("\n--- Same engine configured for streaming mode ---")
    # The registry also builds a streaming-configured engine. Streaming keeps
    # working memory across calls and reports activation *deltas*; it also
    # requires hashable fact values, so it is not a drop-in for the list-valued
    # facts above. See 20_streaming_mode.py and 23_streaming_vs_stateless.py for
    # streaming semantics end to end.
    streaming = get_engine("PHREAK", streaming_mode=True)
    streaming.load_rules(rules)
    print(f"stateless engine mode: {stateless.mode}")
    print(f"streaming engine mode: {streaming.mode}")

    print("\nOne pluggable engine, selected by name, in two evaluation modes.")


if __name__ == "__main__":
    main()
