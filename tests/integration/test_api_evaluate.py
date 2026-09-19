import pytest
from fastapi.testclient import TestClient

from fluxrules.api.app import create_app
from fluxrules.api.deps import get_rule_service
from fluxrules.domain.models import EngineRule, RuleCondition, Ruleset

pytest.importorskip("fastapi")


def test_evaluate_and_explain_endpoints() -> None:
    app = create_app()
    service = get_rule_service()
    service.persist(
        Ruleset(
            group="rs1",
            rules=(
                EngineRule(
                    id=1,
                    name="r1",
                    conditions=(RuleCondition("amount", "gt", 100),),
                    actions=("review",),
                ),
            ),
        )
    )

    client = TestClient(app)
    response = client.post("/v1/rulesets/rs1/evaluate", json={"facts": {"amount": 150}})
    assert response.status_code == 200
    body = response.json()
    assert body["matched_rules"] == [1]

    explain = client.get(f"/v1/executions/{body['execution_id']}")
    assert explain.status_code == 200
    assert explain.json()["matched_rules"] == [1]


def test_simulate_endpoint() -> None:
    app = create_app()
    service = get_rule_service()
    service.persist(
        Ruleset(
            group="rs1",
            rules=(
                EngineRule(
                    id=1,
                    name="r1",
                    conditions=(RuleCondition("amount", "gt", 100),),
                    actions=("review",),
                ),
            ),
        )
    )
    client = TestClient(app)
    response = client.post(
        "/v1/rulesets/rs1/simulate",
        json={"samples": [{"amount": 10}, {"amount": 250}]},
    )
    assert response.status_code == 200
    assert response.json()[1]["matched_rules"] == [1]
