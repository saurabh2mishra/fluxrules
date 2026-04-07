"""Sample application to test FluxRules event execution via /api/v1/event.

Usage:
    cd backend
    python simulation/sample_event_app.py \
      --base-url http://localhost:8000/api/v1 \
      --username demo_user \
      --password demo_pass

What it does:
1) Registers/logs in a user
2) Creates a demo rule (idempotent by name)
3) Runs /rules/simulate to preview matched rule(s)
4) Calls /event to execute the runtime pipeline
5) Reads /analytics/runtime so users can observe processing impact
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

import httpx


DEMO_RULE_NAME = "sample_app_high_value_us_event"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample FluxRules event execution client")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1", help="FluxRules API base URL")
    parser.add_argument("--username", default="sample_app_user", help="Username for authentication")
    parser.add_argument("--password", default="sample_app_pass123", help="Password for authentication")
    parser.add_argument("--email", default="sample_app_user@example.com", help="Email for user registration")
    parser.add_argument("--role", default="business", help="Role for registration")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    return parser.parse_args()


def register_if_needed(client: httpx.Client, base_url: str, username: str, email: str, password: str, role: str) -> None:
    response = client.post(
        f"{base_url}/auth/register",
        json={"username": username, "email": email, "password": password, "role": role},
    )
    # idempotent: treat already-registered as okay
    if response.status_code in {200, 400}:
        return
    response.raise_for_status()


def login(client: httpx.Client, base_url: str, username: str, password: str) -> str:
    response = client.post(
        f"{base_url}/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but no access_token in response")
    return token


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ensure_demo_rule(client: httpx.Client, base_url: str, headers: Dict[str, str]) -> Optional[int]:
    rules = client.get(f"{base_url}/rules", headers=headers)
    rules.raise_for_status()
    for rule in rules.json():
        if rule.get("name") == DEMO_RULE_NAME:
            return int(rule["id"])

    rule_payload = {
        "name": DEMO_RULE_NAME,
        "description": "Demo rule from sample_event_app to test /event execution",
        "group": "sample-app",
        "priority": 77,
        "enabled": True,
        "condition_dsl": {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "amount", "op": ">", "value": 1000},
                {"type": "condition", "field": "country", "op": "==", "value": "US"},
            ],
        },
        "action": "sample_app_action",
    }

    create = client.post(f"{base_url}/rules?skip_conflict_check=true", json=rule_payload, headers=headers)
    create.raise_for_status()
    return int(create.json()["id"])


def run_simulation(client: httpx.Client, base_url: str, headers: Dict[str, str], event_payload: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(f"{base_url}/rules/simulate", json={"event": event_payload}, headers=headers)
    response.raise_for_status()
    return response.json()


def run_event_execution(client: httpx.Client, base_url: str, headers: Dict[str, str], event_payload: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(
        f"{base_url}/event",
        json={"event_type": "sample_app_event", "data": event_payload, "metadata": {"source": "sample_event_app"}},
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


def get_runtime_analytics(client: httpx.Client, base_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    response = client.get(f"{base_url}/analytics/runtime", headers=headers)
    response.raise_for_status()
    return response.json()


def main() -> None:
    args = parse_args()
    event_payload = {"amount": 2500, "country": "US", "transaction_type": "transfer"}

    with httpx.Client(timeout=args.timeout) as client:
        register_if_needed(client, args.base_url, args.username, args.email, args.password, args.role)
        token = login(client, args.base_url, args.username, args.password)
        headers = auth_headers(token)

        rule_id = ensure_demo_rule(client, args.base_url, headers)
        simulation = run_simulation(client, args.base_url, headers, event_payload)
        execution = run_event_execution(client, args.base_url, headers, event_payload)
        runtime = get_runtime_analytics(client, args.base_url, headers)

    matched = simulation.get("matched_rules", [])
    print("\n=== FluxRules Sample App Result ===")
    print(f"Demo rule id: {rule_id}")
    print(f"Simulate matched count: {len(matched)}")
    if matched:
        print("Matched rules:")
        for item in matched:
            print(f"  - {item.get('id')} :: {item.get('name')} :: action={item.get('action')}")

    print(f"/event response: {execution}")
    summary = runtime.get("summary", {})
    print(
        "Runtime summary (post-call): "
        f"events_processed={summary.get('events_processed')}, "
        f"rules_fired={summary.get('rules_fired')}, "
        f"coverage_pct={summary.get('coverage_pct')}"
    )


if __name__ == "__main__":
    main()
