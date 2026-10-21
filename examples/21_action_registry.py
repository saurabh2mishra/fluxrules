"""Batch 3 example: what the action registry knows about each action.

Registering a handler with ``@action`` records more than the function. The
registry keeps a description and a category for each action, inspects its
parameters, and can run it synchronously or, for ``async_handler=True``, with
``await``. This lets a service list its actions, group them, and check a call's
arguments before running it.

See 15_action_system.py for dispatching fired actions after evaluation.
"""

from __future__ import annotations

import asyncio

from shared_use_case import SHARED_FACTS, USE_CASE_NAME

from fluxrules.plugins.actions import action, action_registry


@action(name="notify_risk_team", description="Post to the risk team channel", category="notifications")
def notify_risk_team(fact_id: str, reason: str = "rule fired") -> dict:
    return {"notified": "risk-team", "fact_id": fact_id, "reason": reason}


@action(name="email_customer", description="Email the cardholder", category="notifications")
def email_customer(fact_id: str, template: str = "payment_on_hold") -> dict:
    return {"emailed": True, "fact_id": fact_id, "template": template}


@action(
    name="record_case",
    description="Store a case in the case system",
    category="case_management",
    async_handler=True,
)
async def record_case(fact_id: str, amount: float) -> dict:
    await asyncio.sleep(0)  # stands in for a database or HTTP call
    return {"case_id": f"case-{fact_id}", "amount": amount}


def main() -> None:
    print("=" * 80)
    print("21_action_registry.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    print("\nRegistered actions:")
    for name in sorted(action_registry.list_actions()):
        info = action_registry.get(name)
        print(f"  {info.name:18} category={info.category:16} {info.description}")

    notifications = action_registry.get_actions_by_category("notifications")
    print(f"\nIn category 'notifications': {sorted(a.name for a in notifications)}")

    print(f"\nParameters of notify_risk_team: {action_registry.get_action_signature('notify_risk_team')}")

    fact = SHARED_FACTS[0]
    print(f"\nRun handlers for {fact['fact_id']}:")
    print(f"  sync:  {action_registry.execute('notify_risk_team', fact_id=fact['fact_id'])}")
    case = asyncio.run(
        action_registry.execute_async("record_case", fact_id=fact["fact_id"], amount=fact["amount"])
    )
    print(f"  async: {case}")


if __name__ == "__main__":
    main()
