"""POST /api/v1/sessions/{id}/evaluate evaluates each stored fact on its own.

Facts are never merged: two transactions with the same fields each get their
own answer, the same answer /evaluate/bulk gives for them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

RULES = [
    {
        "name": "big_payment",
        "group": "payments",
        "priority": 10,
        "action": "review",
        "conditions": {"type": "condition", "field": "amount", "op": ">", "value": 1000},
    },
    {
        "name": "german_payment",
        "group": "payments",
        "action": "add_vat",
        "conditions": {"type": "condition", "field": "country", "op": "==", "value": "DE"},
    },
    {
        "name": "other_group",
        "group": "marketing",
        "action": "promo",
        "conditions": {"type": "condition", "field": "amount", "op": ">", "value": 0},
    },
]
TXN_1 = {"amount": 4200, "country": "DE"}
TXN_2 = {"amount": 50, "country": "US"}


@pytest.fixture()
def session_url(client):  # type: ignore[no-untyped-def]
    for rule in RULES:
        assert client.post("/api/v1/rules", json=rule).status_code == 200
    session_id = client.post("/api/v1/sessions", json={}).json()["id"]
    url = f"/api/v1/sessions/{session_id}"
    client.post(f"{url}/facts", json={"fact_id": "txn_1", "fact": TXN_1})
    client.post(f"{url}/facts", json={"fact_id": "txn_2", "fact": TXN_2})
    return url


def test_each_fact_is_evaluated_separately(client, session_url) -> None:  # type: ignore[no-untyped-def]
    body = client.post(f"{session_url}/evaluate", json={"ruleset_id": "payments"}).json()
    assert body["count"] == 2
    assert body["ruleset_group"] == "payments"
    results = [(r["index"], r["fact_id"], r["matched_rules"]) for r in body["results"]]
    # Merging would have let txn_2 overwrite txn_1 and match nothing.
    assert results == [(0, "txn_1", [1, 2]), (1, "txn_2", [])]
    assert body["results"][0]["actions"] == ["review", "add_vat"]


def test_same_answers_as_bulk(client, session_url) -> None:  # type: ignore[no-untyped-def]
    session = client.post(f"{session_url}/evaluate", json={"ruleset_id": "payments"}).json()
    bulk = client.post(
        "/api/v1/evaluate/bulk", json={"facts": [TXN_1, TXN_2], "ruleset_id": "payments"}
    ).json()
    assert [r["matched_rules"] for r in session["results"]] == [
        r["matched_rules"] for r in bulk["results"]
    ]


def test_without_a_body_all_stored_rules_are_used(client, session_url) -> None:  # type: ignore[no-untyped-def]
    body = client.post(f"{session_url}/evaluate").json()
    assert body["ruleset_group"] == "all"
    assert 3 in body["results"][1]["matched_rules"]  # the marketing rule


def test_rule_ids(client, session_url) -> None:  # type: ignore[no-untyped-def]
    body = client.post(f"{session_url}/evaluate", json={"rule_ids": [2]}).json()
    assert [r["matched_rules"] for r in body["results"]] == [[2], []]


def test_session_is_not_changed(client, session_url) -> None:  # type: ignore[no-untyped-def]
    before = client.get(f"{session_url}/facts").json()
    client.post(f"{session_url}/evaluate")
    assert client.get(f"{session_url}/facts").json() == before


def test_replaced_fact_keeps_its_place(client, session_url) -> None:  # type: ignore[no-untyped-def]
    client.post(f"{session_url}/facts", json={"fact_id": "txn_1", "fact": {"amount": 1}})
    body = client.post(f"{session_url}/evaluate", json={"ruleset_id": "payments"}).json()
    assert [(r["fact_id"], r["matched_rules"]) for r in body["results"]] == [
        ("txn_1", []),
        ("txn_2", []),
    ]


def test_results_can_be_explained(client, session_url) -> None:  # type: ignore[no-untyped-def]
    body = client.post(f"{session_url}/evaluate", json={"ruleset_id": "payments"}).json()
    execution_id = body["results"][0]["execution_id"]
    explained = client.get(f"/api/v1/explain/{execution_id}").json()
    assert explained["matched_rules"] == [1, 2]
    assert explained["facts"] == TXN_1


def test_empty_session(client) -> None:  # type: ignore[no-untyped-def]
    session_id = client.post("/api/v1/sessions", json={}).json()["id"]
    body = client.post(f"/api/v1/sessions/{session_id}/evaluate").json()
    assert (body["count"], body["results"]) == (0, [])


def test_unknown_session_is_404(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post("/api/v1/sessions/missing/evaluate").status_code == 404
