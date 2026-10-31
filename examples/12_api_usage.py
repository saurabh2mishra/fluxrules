"""Batch 2 example: evaluate rules over the HTTP API.

Installing ``fluxrules[api]`` gives you a FastAPI app from ``create_app()``. A
ruleset is stored under a group name, then evaluated over HTTP:

- ``POST /v1/rulesets/{group}/evaluate`` evaluates one fact and returns the
  matched rules, the actions and an ``execution_id``;
- ``GET /v1/executions/{execution_id}`` explains a past evaluation;
- ``POST /v1/rulesets/{group}/simulate`` evaluates a batch of sample facts.

This example runs the real app in-process with FastAPI's ``TestClient``, so no
server is needed. In production you would run ``fluxrules serve``.
"""

from __future__ import annotations

import json

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules

try:
    from fastapi.testclient import TestClient

    from fluxrules.api.app import create_app
    from fluxrules.api.deps import get_rule_service
except ImportError:  # pragma: no cover - depends on installed extras
    raise SystemExit("This example needs the API extra: pip install 'fluxrules[api]'") from None

from fluxrules.domain.models import Ruleset

GROUP = "payment_risk"


def main() -> None:
    print("=" * 80)
    print("12_api_usage.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    app = create_app()
    rules = tuple(rule.to_engine_rule(group=GROUP) for rule in build_shared_rules())
    get_rule_service().persist(Ruleset(group=GROUP, rules=rules))
    client = TestClient(app)

    execution_id = None
    for fact in SHARED_FACTS:
        response = client.post(f"/v1/rulesets/{GROUP}/evaluate", json={"facts": fact})
        body = response.json()
        execution_id = execution_id or body["execution_id"]
        print(f"\nPOST /v1/rulesets/{GROUP}/evaluate  ({fact['fact_id']})")
        print(
            f"  {response.status_code} matched_rules={body['matched_rules']} actions={body['actions']}"
        )

    explained = client.get(f"/v1/executions/{execution_id}")
    print(f"\nGET /v1/executions/{execution_id}")
    print(f"  {explained.status_code} {json.dumps(explained.json())[:160]}...")

    samples = [{**SHARED_FACTS[0], "ip_risk_score": score} for score in (50, 90)]
    simulated = client.post(f"/v1/rulesets/{GROUP}/simulate", json={"samples": samples})
    print(f"\nPOST /v1/rulesets/{GROUP}/simulate  (txn-001 with IP risk 50 and 90)")
    for score, run in zip((50, 90), simulated.json(), strict=True):
        print(f"  ip_risk_score={score}: matched_rules={run['matched_rules']}")


if __name__ == "__main__":
    main()
