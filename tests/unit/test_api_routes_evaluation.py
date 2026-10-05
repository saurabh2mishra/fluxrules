"""Tests for evaluation and explanation API endpoints."""

from __future__ import annotations


class TestEvaluateEndpoint:
    def test_evaluate_with_db_rules(self, client, rule_payload):
        # Create a rule first
        client.post(
            "/api/v1/rules",
            json=rule_payload(
                "AgeCheck",
                action="allow_access",
                field="age",
                op=">",
                value=18,
                group="access",
                priority=1,
                enabled=True,
            ),
        )

        resp = client.post(
            "/api/v1/evaluate",
            json={"facts": {"age": 25}, "ruleset_id": "access"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_id" in data
        assert "matched_rules" in data
        assert "actions" in data

    def test_evaluate_no_match(self, client, rule_payload):
        client.post(
            "/api/v1/rules",
            json=rule_payload(
                "HighVal",
                action="flag",
                field="amount",
                op=">",
                value=10000,
                group="finance",
                priority=1,
                enabled=True,
            ),
        )

        resp = client.post(
            "/api/v1/evaluate",
            json={"facts": {"amount": 50}, "ruleset_id": "finance"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched_rules"] == []

    def test_evaluate_all_rules(self, client):
        resp = client.post(
            "/api/v1/evaluate",
            json={"facts": {"x": 1}},
        )
        assert resp.status_code == 200

    def test_explain_after_evaluate(self, client, rule_payload):
        client.post(
            "/api/v1/rules",
            json=rule_payload(
                "ExplRule",
                action="grant_vip",
                field="status",
                op="==",
                value="vip",
                group="test",
                priority=1,
                enabled=True,
            ),
        )

        eval_resp = client.post(
            "/api/v1/evaluate",
            json={"facts": {"status": "vip"}, "ruleset_id": "test"},
        )
        execution_id = eval_resp.json()["execution_id"]

        explain_resp = client.get(f"/api/v1/explain/{execution_id}")
        assert explain_resp.status_code == 200
        data = explain_resp.json()
        assert data["execution_id"] == execution_id

    def test_explain_not_found(self, client):
        resp = client.get("/api/v1/explain/nonexistent-id")
        assert resp.status_code == 404


class TestBulkEvaluateEndpoint:
    def test_bulk_evaluate_returns_one_result_per_fact_set(self, client, rule_payload):
        client.post(
            "/api/v1/rules?skip_conflict_check=true",
            json=rule_payload(
                "BulkAge",
                action="allow_access",
                field="age",
                op=">",
                value=18,
                group="bulk_access",
                priority=1,
                enabled=True,
            ),
        )

        resp = client.post(
            "/api/v1/evaluate/bulk",
            json={
                "facts": [{"age": 25}, {"age": 10}, {"age": 40}],
                "ruleset_id": "bulk_access",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert data["ruleset_group"] == "bulk_access"
        results = data["results"]
        assert [r["index"] for r in results] == [0, 1, 2]
        # Each fact set gets its own execution id.
        execution_ids = {r["execution_id"] for r in results}
        assert len(execution_ids) == 3
        for result in results:
            assert "matched_rules" in result
            assert "actions" in result

    def test_bulk_evaluate_execution_ids_are_explainable(self, client, rule_payload):
        client.post(
            "/api/v1/rules?skip_conflict_check=true",
            json=rule_payload(
                "BulkExpl",
                action="grant_vip",
                field="status",
                op="==",
                value="vip",
                group="bulk_expl",
                priority=1,
                enabled=True,
            ),
        )

        resp = client.post(
            "/api/v1/evaluate/bulk",
            json={
                "facts": [{"status": "vip"}, {"status": "regular"}],
                "ruleset_id": "bulk_expl",
            },
        )
        results = resp.json()["results"]

        # Each execution is retrievable and echoes its own fact set.
        first = client.get(f"/api/v1/explain/{results[0]['execution_id']}")
        second = client.get(f"/api/v1/explain/{results[1]['execution_id']}")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["facts"] == {"status": "vip"}
        assert second.json()["facts"] == {"status": "regular"}

    def test_bulk_evaluate_empty_facts(self, client):
        resp = client.post("/api/v1/evaluate/bulk", json={"facts": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_bulk_evaluate_without_rules_returns_empty_matches(self, client):
        resp = client.post(
            "/api/v1/evaluate/bulk",
            json={"facts": [{"age": 25}], "ruleset_id": "missing_ruleset"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ruleset_group"] == "missing_ruleset"
        assert data["results"][0]["matched_rules"] == []
        assert data["results"][0]["actions"] == []


class TestRulesetsEndpoint:
    def test_list_rulesets(self, client, rule_payload):
        r1 = client.post(
            "/api/v1/rules",
            json=rule_payload("R1_grpa", action="act_a", group="grp_a", priority=1),
        )
        r2 = client.post(
            "/api/v1/rules",
            json=rule_payload(
                "R2_grpb", action="act_b", field="y", value=2, group="grp_b", priority=2
            ),
        )
        assert r1.status_code == 200, f"R1 creation failed: {r1.json()}"
        assert r2.status_code == 200, f"R2 creation failed: {r2.json()}"
        resp = client.get("/api/v1/rulesets")
        assert resp.status_code == 200
        data = resp.json()
        groups = [r["group"] for r in data]
        assert "grp_a" in groups
        assert "grp_b" in groups

    def test_list_rulesets_pagination(self, client, rule_payload):
        for i in range(3):
            r = client.post(
                "/api/v1/rules?skip_conflict_check=true",
                json=rule_payload(f"RPage{i}", action=f"act_{i}", value=i, group=f"page_grp_{i}"),
            )
            assert r.status_code == 200, f"creation failed: {r.json()}"

        first = client.get("/api/v1/rulesets", params={"skip": 0, "limit": 2})
        assert first.status_code == 200
        assert len(first.json()) == 2

        second = client.get("/api/v1/rulesets", params={"skip": 2, "limit": 2})
        assert second.status_code == 200

        first_groups = {r["group"] for r in first.json()}
        second_groups = {r["group"] for r in second.json()}
        assert first_groups.isdisjoint(second_groups)

    def test_list_rulesets_rejects_invalid_limit(self, client):
        resp = client.get("/api/v1/rulesets", params={"limit": 0})
        assert resp.status_code == 422

    def test_get_ruleset(self, client, rule_payload):
        client.post(
            "/api/v1/rules",
            json=rule_payload("RGet", group="fetch_grp"),
        )
        resp = client.get("/api/v1/rulesets/fetch_grp")
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"] == "fetch_grp"
        assert len(data["rules"]) >= 1

    def test_get_ruleset_not_found(self, client):
        resp = client.get("/api/v1/rulesets/nonexistent")
        assert resp.status_code == 404

    def test_update_ruleset(self, client, rule_payload):
        client.post(
            "/api/v1/rules",
            json=rule_payload("RUpd", group="upd_grp", enabled=True),
        )
        resp = client.put(
            "/api/v1/rulesets/upd_grp",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] >= 1


class TestAuditLogs:
    def test_get_audit_logs(self, client, rule_payload):
        # Create a rule to generate audit logs
        client.post("/api/v1/rules", json=rule_payload("AuditRule"))
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
