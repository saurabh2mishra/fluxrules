"""Tests for rule API endpoints."""

from __future__ import annotations


class TestRuleEndpoints:
    def test_create_rule(self, client, rule_payload):
        resp = client.post(
            "/api/v1/rules",
            json=rule_payload(
                "TestRule",
                action="allow",
                field="age",
                op=">",
                value=18,
                description="desc",
                group="grp",
                priority=1,
                enabled=True,
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "TestRule"
        assert isinstance(data["id"], int)

    def test_list_rules(self, client, rule_payload):
        # Create one first
        client.post("/api/v1/rules", json=rule_payload("ListRule"))
        resp = client.get("/api/v1/rules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_rule(self, client, rule_payload):
        create = client.post("/api/v1/rules", json=rule_payload("GetRule"))
        rule_id = create.json()["id"]
        resp = client.get(f"/api/v1/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetRule"

    def test_get_rule_not_found(self, client):
        resp = client.get("/api/v1/rules/99999")
        assert resp.status_code == 404

    def test_update_rule(self, client, rule_payload):
        create = client.post("/api/v1/rules", json=rule_payload("UpdRule", action="old"))
        rule_id = create.json()["id"]
        resp = client.put(
            f"/api/v1/rules/{rule_id}",
            json={"name": "UpdRuleNew", "action": "new"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "UpdRuleNew"

    def test_delete_rule(self, client, rule_payload):
        create = client.post("/api/v1/rules", json=rule_payload("DelRule"))
        rule_id = create.json()["id"]
        resp = client.delete(f"/api/v1/rules/{rule_id}")
        assert resp.status_code == 200
        # Verify deleted
        resp2 = client.get(f"/api/v1/rules/{rule_id}")
        assert resp2.status_code == 404

    def test_validate_rule(self, client, rule_payload):
        resp = client.post("/api/v1/rules/validate", json=rule_payload("ValidRule"))
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data


class TestHealthAndSystem:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_system_status(self, client):
        resp = client.get("/api/v1/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert data["status"] == "running"
        # The endpoint reports per-component health via HealthCheckService.
        assert data["healthy"] is True
        assert set(data["components"]) == {"queue", "cache", "persistence"}
        for component in data["components"].values():
            assert component["healthy"] is True
            assert isinstance(component["message"], str)
