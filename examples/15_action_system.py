"""Batch 3 example: run code when a rule fires.

A rule's ``action`` is a name. ``evaluate()`` returns the names of the actions
that fired, in priority order, and leaves running them to your application. The
action registry connects a name to a handler function:

1. register a handler for each action name with ``@action``;
2. evaluate the fact;
3. pass each fired action name to ``action_registry.execute``.

Keeping evaluation separate from execution means the same rules can drive a
real payment system in production and a dry run in tests.
"""

from __future__ import annotations

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine
from fluxrules.plugins.actions import action, action_registry


@action(name="block_payment", category="payments")
def block_payment(fact_id: str, amount: float, **_: object) -> dict:
    return {"status": "blocked", "fact_id": fact_id, "amount": amount}


@action(name="manual_review", category="operations")
def manual_review(fact_id: str, **_: object) -> dict:
    return {"status": "queued_for_review", "fact_id": fact_id}


@action(name="step_up_auth", category="identity")
def step_up_auth(fact_id: str, email_domain: str, **_: object) -> dict:
    return {"status": "challenge_sent", "fact_id": fact_id, "to": email_domain}


def main() -> None:
    print("=" * 80)
    print("15_action_system.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    engine = PhreakEngine()
    engine.load_rules(build_shared_rules())

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(f"\n{fact['fact_id']}: fired actions={result.actions}")
        if not result.actions:
            print("  nothing to run, payment approved")
        for name in result.actions:
            outcome = action_registry.execute(name, **fact)
            print(f"  ran {name:14} -> {outcome}")


if __name__ == "__main__":
    main()
