"""The /api/v1/engines endpoints behave as docs/rest-api.md describes.

Includes the endpoints the docs list as "not finished": these tests pin what
they do today, so making them real must update the docs and this file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from tests.integration.test_rest_api_reference import BIG, FACT, GERMAN  # noqa: E402


@pytest.fixture()
def api(client):  # type: ignore[no-untyped-def]
    for rule in (BIG, GERMAN):
        assert client.post("/api/v1/rules", json=rule).status_code == 200
    return client


def test_evaluate(api) -> None:  # type: ignore[no-untyped-def]
    body = api.post("/api/v1/engines/evaluate", json={"event": FACT, "rule_ids": [1, 2]}).json()
    assert body["matched_rules"] == [
        {"id": 1, "name": "big_payment", "priority": 10},
        {"id": 2, "name": "german_payment", "priority": 0},
    ]
    assert body["execution_order"] == [1, 2]
    assert set(body["explanations"]) == {"1", "2"}
    assert set(body["stats"]) == {"latency_ms", "rules_evaluated", "rules_matched"}
    assert (body["engine_type"], body["dry_run"]) == ("PHREAK", False)


def test_simulate_matches_evaluate(api) -> None:  # type: ignore[no-untyped-def]
    evaluated = api.post("/api/v1/engines/evaluate", json={"event": FACT}).json()
    simulated = api.post("/api/v1/engines/simulate", json={"event": FACT}).json()
    assert simulated["dry_run"] is True
    assert simulated["matched_rules"] == evaluated["matched_rules"]


def test_rule_ids_limit_the_run(api) -> None:  # type: ignore[no-untyped-def]
    body = api.post("/api/v1/engines/simulate", json={"event": FACT, "rule_ids": [2]}).json()
    assert [r["id"] for r in body["matched_rules"]] == [2]


def test_unknown_engine_is_400(api) -> None:  # type: ignore[no-untyped-def]
    response = api.post("/api/v1/engines/evaluate", json={"event": FACT, "engine_type": "RETE"})
    assert response.status_code == 400


def test_new_rule_is_used_on_the_next_request(api) -> None:  # type: ignore[no-untyped-def]
    # Without Redis (as here), a stored rule is used from the next request on.
    third = {
        **BIG,
        "name": "any_amount",
        "priority": 5,
        "conditions": {"type": "condition", "field": "amount", "op": ">", "value": 0},
    }
    api.post("/api/v1/engines/evaluate", json={"event": FACT})
    assert api.post("/api/v1/rules", json=third).status_code == 200
    body = api.post("/api/v1/engines/evaluate", json={"event": FACT}).json()
    assert "any_amount" in [r["name"] for r in body["matched_rules"]]


def test_config_and_available(api) -> None:  # type: ignore[no-untyped-def]
    config = api.get("/api/v1/engines/config").json()
    assert (config["current_engine"], config["available_engines"]) == ("PHREAK", ["PHREAK"])
    available = api.get("/api/v1/engines/available").json()
    assert set(available["descriptions"]) == {"PHREAK"}


class TestNotFinished:
    """Pinned as documented: these answer but do not do what their names say."""

    def test_switch_and_reload_change_nothing(self, api) -> None:  # type: ignore[no-untyped-def]
        assert api.post("/api/v1/engines/switch", json="PHREAK").json()["status"] == "success"
        assert api.post("/api/v1/engines/reload").json()["status"] == "success"
        body = api.post("/api/v1/engines/evaluate", json={"event": FACT}).json()
        assert [r["id"] for r in body["matched_rules"]] == [1, 2]

    def test_stats_report_an_engine_with_no_rules(self, api) -> None:  # type: ignore[no-untyped-def]
        assert api.get("/api/v1/engines/stats").json()["rules_loaded"] == 0

    def test_benchmark_runs_generated_events(self, api) -> None:  # type: ignore[no-untyped-def]
        body = api.post("/api/v1/engines/benchmark?num_events=10").json()
        assert body["num_events"] == 10
        assert "p95" in body["latency_ms"]
