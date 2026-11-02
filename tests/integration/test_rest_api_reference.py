"""The requests and responses shown in docs/rest-api.md match the server.

Each test sends the request the page shows and checks the fields the page
describes, so the reference cannot drift from the routes again.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

BIG = {
    "name": "big_payment",
    "group": "payments",
    "priority": 10,
    "action": "review",
    "conditions": {"type": "condition", "field": "amount", "op": ">", "value": 1000},
}
GERMAN = {
    "name": "german_payment",
    "group": "payments",
    "action": "add_vat",
    "conditions": {"type": "condition", "field": "country", "op": "==", "value": "DE"},
}
FACT = {"amount": 4200, "country": "DE"}


def test_rules_and_evaluation(client) -> None:  # type: ignore[no-untyped-def]
    # One test on purpose: each rule write is slow on a machine without Redis
    # (the engine adapter waits for a connection), so the rules are created
    # once and every section of the page is checked against them.

    # POST /api/v1/rules
    big = client.post("/api/v1/rules", json=BIG).json()
    assert (big["id"], big["current_version"], big["priority"]) == (1, 1, 10)
    assert client.post("/api/v1/rules", json=GERMAN).status_code == 200

    # GET /api/v1/rules: priority defaults to 0
    rules = {r["name"]: r for r in client.get("/api/v1/rules").json()}
    assert rules["german_payment"]["priority"] == 0

    # POST /api/v1/evaluate
    body = client.post("/api/v1/evaluate", json={"facts": FACT, "ruleset_id": "payments"}).json()
    assert body["matched_rules"] == [1, 2]
    assert body["actions"] == ["review", "add_vat"]
    assert body["ruleset_group"] == "payments"
    assert body["facts"] == FACT
    assert body["execution_id"]

    everything = client.post("/api/v1/evaluate", json={"facts": FACT}).json()
    assert (everything["ruleset_group"], everything["matched_rules"]) == ("all", [1, 2])

    only_one = client.post("/api/v1/evaluate", json={"facts": FACT, "rule_ids": [1]}).json()
    assert only_one["matched_rules"] == [1]

    # POST /api/v1/evaluate/bulk
    facts = [FACT, {"amount": 50, "country": "US"}]
    bulk = client.post(
        "/api/v1/evaluate/bulk", json={"facts": facts, "ruleset_id": "payments"}
    ).json()
    assert bulk["count"] == 2
    assert [r["index"] for r in bulk["results"]] == [0, 1]
    assert [r["matched_rules"] for r in bulk["results"]] == [[1, 2], []]

    # GET /api/v1/explain/{execution_id}
    again = client.get(f"/api/v1/explain/{body['execution_id']}").json()
    assert again["matched_rules"] == [1, 2]
    assert again["facts"] == FACT
    assert client.get("/api/v1/explain/unknown").status_code == 404

    # POST /api/v1/rules/simulate
    sim = client.post("/api/v1/rules/simulate", json={"event": FACT, "rule_ids": [1, 2]}).json()
    assert sim["execution_order"] == [1, 2]
    assert set(sim["explanations"]) == {"1", "2"}
    assert sim["dry_run"] is True
    assert sim["stats"]["rules_matched"] == 2
    assert sim["stats"]["total_rules"] is None  # not filled in
    assert sim["stats"]["candidates_evaluated"] == 2
    assert sim["stats"]["evaluation_time_ms"] is not None
    # Real names and priorities, not placeholders.
    assert [(r["id"], r["name"], r["priority"]) for r in sim["matched_rules"]] == [
        (1, "big_payment", 10),
        (2, "german_payment", 0),
    ]

    # /api/v1/engines/evaluate uses the same adapter.
    engines = client.post("/api/v1/engines/evaluate", json={"event": FACT}).json()
    assert [r["name"] for r in engines["matched_rules"]] == ["big_payment", "german_payment"]
    assert set(engines["stats"]) >= {"latency_ms", "rules_evaluated", "rules_matched"}

    # A conflicting rule is refused and parked, unless the check is skipped.
    clash = {**BIG, "name": "other", "conditions": GERMAN["conditions"]}
    refused = client.post("/api/v1/rules", json=clash)
    assert refused.status_code == 400
    assert refused.json()["detail"]["parked"] is True
    forced = client.post("/api/v1/rules?skip_conflict_check=true", json=clash)
    assert forced.status_code == 200


class TestValidate:
    def test_valid_rule_set(self, client) -> None:  # type: ignore[no-untyped-def]
        rule = {"id": 1, "name": "big_payment", "conditions": BIG["conditions"]}
        body = client.post("/validate", json={"ruleset": {"group": "payments", "rules": [rule]}})
        assert body.status_code == 200
        assert body.json() == {"issues": []}

    def test_empty_rule_set(self, client) -> None:  # type: ignore[no-untyped-def]
        body = client.post("/validate", json={"ruleset": {"group": "payments", "rules": []}})
        assert body.json() == {"issues": ["Ruleset is empty"]}

    def test_unknown_operator_is_422(self, client) -> None:  # type: ignore[no-untyped-def]
        bad = {"type": "condition", "field": "a", "op": "??", "value": 1}
        rule = {"id": 1, "name": "x", "conditions": bad}
        response = client.post("/validate", json={"ruleset": {"group": "g", "rules": [rule]}})
        assert response.status_code == 422


class TestSessions:
    def test_create_and_add_fact(self, client) -> None:  # type: ignore[no-untyped-def]
        created = client.post("/api/v1/sessions", json={"metadata": {"channel": "web"}})
        assert created.status_code == 201
        session = created.json()
        assert (session["metadata"], session["fact_count"]) == ({"channel": "web"}, 0)

        url = f"/api/v1/sessions/{session['id']}/facts"
        added = client.post(url, json={"fact_id": "txn_123", "fact": {"amount": 5000}})
        assert added.json()["fact"] == {"amount": 5000}
        client.post(url, json={"fact_id": "txn_123", "fact": {"amount": 7000}})
        facts = client.get(url).json()
        assert [f["fact"] for f in facts] == [{"amount": 7000}]  # same fact_id replaces

        evaluated = client.post(f"/api/v1/sessions/{session['id']}/evaluate").json()
        assert evaluated["count"] == 1
        assert evaluated["results"][0]["fact_id"] == "txn_123"


class TestHealthAndErrors:
    def test_health(self, client) -> None:  # type: ignore[no-untyped-def]
        assert client.get("/health").json() == {"status": "healthy"}

    def test_system_status(self, client) -> None:  # type: ignore[no-untyped-def]
        body = client.get("/api/v1/system/status").json()
        assert body["status"] == "running"
        assert {"queue", "cache", "persistence"} <= set(body["components"])

    def test_wrong_body_shape_is_422(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.post("/api/v1/evaluate", json={"fact": {}})
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "facts"]


def test_register_and_token(client) -> None:  # type: ignore[no-untyped-def]
    user = {"username": "alice", "email": "alice@example.com", "password": "Str0ng-Passw0rd!"}
    assert client.post("/api/v1/auth/register", json=user).status_code == 200
    token = client.post(
        "/api/v1/auth/token", data={"username": "alice", "password": "Str0ng-Passw0rd!"}
    ).json()
    assert token["token_type"] == "bearer"
    assert token["access_token"]


def test_explain_forgets_the_oldest_evaluations(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fluxrules.api.config import settings
    from fluxrules.api.routes.evaluation import _execution_store

    monkeypatch.setattr(settings, "EXPLAIN_STORE_MAX_RECORDS", 2)
    _execution_store.clear()
    ids = [
        client.post("/api/v1/evaluate", json={"facts": FACT}).json()["execution_id"]
        for _ in range(3)
    ]
    assert client.get(f"/api/v1/explain/{ids[0]}").status_code == 404
    assert [client.get(f"/api/v1/explain/{i}").status_code for i in ids[1:]] == [200, 200]
