"""
Verification script: Confirms that brms_overlap conflicts are properly
blocked/parked so no two overlapping rules can both be active.

Run:  cd backend && uv run python simulation/verify_conflicts.py
Requires: backend server running at localhost:8000
"""
import asyncio
import httpx
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"
auth_token = None

PASS = "✅"
FAIL = "❌"
INFO = "ℹ️ "
results = []


def report(name: str, passed: bool, detail: str = ""):
    tag = PASS if passed else FAIL
    results.append((name, passed, detail))
    print(f"  {tag} {name}" + (f" — {detail}" if detail else ""))


async def login():
    global auth_token
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE_URL}/auth/token",
                         data={"username": USERNAME, "password": PASSWORD},
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200, f"Login failed: {r.text}"
        auth_token = r.json()["access_token"]


def headers():
    return {"Authorization": f"Bearer {auth_token}"}


async def delete_all_rules(client):
    """Delete every rule so we start clean."""
    deleted = 0
    while True:
        r = await client.get(f"{BASE_URL}/rules?limit=200", headers=headers())
        rules = r.json()
        if not rules:
            break
        for rule in rules:
            await client.delete(f"{BASE_URL}/rules/{rule['id']}", headers=headers())
            deleted += 1
    # Also clean parked conflicts
    r = await client.get(f"{BASE_URL}/rules/conflicts/parked?status=pending", headers=headers())
    if r.status_code == 200:
        for item in r.json():
            await client.delete(f"{BASE_URL}/rules/conflicts/parked/{item['id']}", headers=headers())
    print(f"  Cleaned up {deleted} active rules + parked conflicts")


async def run_verification():
    await login()
    print(f"\n{'='*65}")
    print("CONFLICT HANDLING VERIFICATION")
    print(f"{'='*65}")

    async with httpx.AsyncClient(timeout=60.0) as client:

        # ── Cleanup ──
        print("\n[0] Cleaning up...")
        await delete_all_rules(client)

        # ==================================================================
        # TEST 1: Two rules with overlapping conditions → second is parked
        # ==================================================================
        print("\n[1] brms_overlap: second overlapping rule should be BLOCKED & PARKED")

        rule_a = {
            "name": "AcctAge_Over_64_R13",
            "description": "Account age > 64",
            "group": "simple",
            "priority": 13,
            "enabled": True,
            "condition_dsl": {"type": "condition", "field": "account_age", "op": ">", "value": 64},
            "action": "flag_suspicious",
        }
        rule_b = {
            "name": "AcctAge_Over_65_R18",
            "description": "Account age > 65",
            "group": "simple",
            "priority": 18,
            "enabled": True,
            "condition_dsl": {"type": "condition", "field": "account_age", "op": ">", "value": 65},
            "action": "require_review",
        }

        # Create first rule → should succeed
        r1 = await client.post(f"{BASE_URL}/rules", json=rule_a, headers=headers())
        report("Create first overlapping rule (AcctAge_Over_64_R13)",
               r1.status_code == 200,
               f"status={r1.status_code}")

        # Create second rule → should be BLOCKED (400) because it overlaps
        r2 = await client.post(f"{BASE_URL}/rules", json=rule_b, headers=headers())
        blocked = r2.status_code == 400
        detail_json = r2.json() if r2.status_code == 400 else {}
        has_overlap = any(
            c.get("type") == "brms_overlap"
            for c in (detail_json.get("detail", {}).get("conflicts", []))
        )
        is_parked = detail_json.get("detail", {}).get("parked") is True
        report("Second overlapping rule is BLOCKED",
               blocked, f"status={r2.status_code}")
        report("Blocked due to brms_overlap conflict type",
               has_overlap, f"conflicts={detail_json.get('detail', {}).get('conflicts', [])}")
        report("Blocked rule is PARKED for review",
               is_parked)

        # Verify only one rule is active
        r_list = await client.get(f"{BASE_URL}/rules", headers=headers())
        active_names = [r["name"] for r in r_list.json()]
        report("Only AcctAge_Over_64_R13 is active",
               "AcctAge_Over_64_R13" in active_names and "AcctAge_Over_65_R18" not in active_names,
               f"active={active_names}")

        # Verify parked rule exists
        r_parked = await client.get(f"{BASE_URL}/rules/conflicts/parked?status=pending", headers=headers())
        parked_names = [p["name"] for p in r_parked.json()] if r_parked.status_code == 200 else []
        report("AcctAge_Over_65_R18 is in Parked Conflicts",
               "AcctAge_Over_65_R18" in parked_names,
               f"parked={parked_names}")

        # ==================================================================
        # TEST 2: Validate endpoint also flags brms_overlap
        # ==================================================================
        print("\n[2] Validate endpoint reports brms_overlap for overlapping rule")
        r_val = await client.post(f"{BASE_URL}/rules/validate", json=rule_b, headers=headers())
        val_data = r_val.json()
        val_overlaps = [c for c in val_data.get("conflicts", []) if c.get("type") == "brms_overlap"]
        report("Validate endpoint detects brms_overlap",
               len(val_overlaps) > 0,
               f"overlap_conflicts={val_overlaps}")

        # ==================================================================
        # TEST 3: Editing the active rule to itself should NOT self-conflict
        # ==================================================================
        print("\n[3] Editing active rule should not conflict with itself")
        active_rule_id = None
        for r in r_list.json():
            if r["name"] == "AcctAge_Over_64_R13":
                active_rule_id = r["id"]
                break
        if active_rule_id:
            r_val_self = await client.post(
                f"{BASE_URL}/rules/validate?rule_id={active_rule_id}",
                json=rule_a, headers=headers())
            self_conflicts = r_val_self.json().get("conflicts", [])
            report("No self-conflict when editing own rule",
                   not any(str(c.get("existing_rule_id")) == str(active_rule_id) for c in self_conflicts),
                   f"conflicts={self_conflicts}")
        else:
            report("No self-conflict when editing own rule", False, "Could not find active rule ID")

        # ==================================================================
        # TEST 4: Exact duplicate condition+action → blocked
        # ==================================================================
        print("\n[4] Exact duplicate condition+action should be BLOCKED")
        await delete_all_rules(client)
        dup_rule1 = {
            "name": "DupTest1", "description": "d", "group": "dup",
            "priority": 1, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 1000},
            "action": "flag_suspicious",
        }
        dup_rule2 = {
            "name": "DupTest2", "description": "d", "group": "dup2",
            "priority": 2, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 1000},
            "action": "flag_suspicious",
        }
        await client.post(f"{BASE_URL}/rules", json=dup_rule1, headers=headers())
        r_dup = await client.post(f"{BASE_URL}/rules", json=dup_rule2, headers=headers())
        report("Exact duplicate condition+action is blocked",
               r_dup.status_code == 400,
               f"status={r_dup.status_code}")

        # ==================================================================
        # TEST 5: Priority collision → blocked
        # ==================================================================
        print("\n[5] Priority collision should be BLOCKED")
        prio_rule = {
            "name": "PrioTest", "description": "d", "group": "dup",
            "priority": 1, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 50},
            "action": "send_alert",
        }
        r_prio = await client.post(f"{BASE_URL}/rules", json=prio_rule, headers=headers())
        report("Priority collision is blocked",
               r_prio.status_code == 400,
               f"status={r_prio.status_code}")

        # ==================================================================
        # TEST 6: Update that creates overlap → blocked
        # ==================================================================
        print("\n[6] Update creating overlap should be BLOCKED")
        await delete_all_rules(client)
        upd_a = {
            "name": "UpdA", "description": "d", "group": "upd",
            "priority": 10, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 100},
            "action": "flag_high",
        }
        upd_b = {
            "name": "UpdB", "description": "d", "group": "upd",
            "priority": 11, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "score", "op": "<", "value": 10},
            "action": "flag_low",
        }
        r_ua = await client.post(f"{BASE_URL}/rules", json=upd_a, headers=headers())
        r_ub = await client.post(f"{BASE_URL}/rules", json=upd_b, headers=headers())
        upd_b_id = r_ub.json()["id"] if r_ub.status_code == 200 else None
        if upd_b_id:
            upd_overlap = {
                "name": "UpdB", "description": "now overlapping", "group": "upd",
                "priority": 11, "enabled": True,
                "condition_dsl": {"type": "condition", "field": "score", "op": ">", "value": 50},
                "action": "flag_low",
            }
            r_upd = await client.put(f"{BASE_URL}/rules/{upd_b_id}", json=upd_overlap, headers=headers())
            report("Update that creates overlap is blocked",
                   r_upd.status_code == 400,
                   f"status={r_upd.status_code}")
        else:
            report("Update that creates overlap is blocked", False, "Setup failed")

        # ==================================================================
        # TEST 7: Simulation-style rules — run the same generation pattern
        # ==================================================================
        print("\n[7] Simulation-style: create rules like rules_simulation.py does")
        await delete_all_rules(client)

        # Reproduce the exact rules from the user's scenario
        sim_rules = [
            {
                "name": "AcctAge_Over_64_R13",
                "description": "Simple rule #13 for account_age threshold",
                "group": "simple",
                "priority": 50,
                "enabled": True,
                "condition_dsl": {"type": "condition", "field": "account_age", "op": ">", "value": 64},
                "action": "flag_suspicious",
            },
            {
                "name": "AcctAge_Over_65_R18",
                "description": "Simple rule #18 for account_age threshold",
                "group": "simple",
                "priority": 51,
                "enabled": True,
                "condition_dsl": {"type": "condition", "field": "account_age", "op": ">", "value": 65},
                "action": "require_review",
            },
        ]

        r_sim1 = await client.post(f"{BASE_URL}/rules", json=sim_rules[0], headers=headers())
        report("Sim: First rule created",
               r_sim1.status_code == 200,
               f"status={r_sim1.status_code}")

        r_sim2 = await client.post(f"{BASE_URL}/rules", json=sim_rules[1], headers=headers())
        report("Sim: Second overlapping rule is BLOCKED & PARKED",
               r_sim2.status_code == 400,
               f"status={r_sim2.status_code}")

        # Check active rules have no unresolved overlaps
        r_active = await client.get(f"{BASE_URL}/rules", headers=headers())
        active = r_active.json()
        active_names = [r["name"] for r in active]
        both_active = "AcctAge_Over_64_R13" in active_names and "AcctAge_Over_65_R18" in active_names
        report("Both overlapping rules are NOT simultaneously active",
               not both_active,
               f"active={active_names}")

        # Verify conflict detection endpoint shows no conflicts for active rules
        r_detect = await client.get(f"{BASE_URL}/rules/conflicts/detect", headers=headers())
        if r_detect.status_code == 200:
            detected = r_detect.json().get("conflicts", [])
            report("Conflict detection shows no conflicts among active rules",
                   len(detected) == 0,
                   f"conflicts_count={len(detected)}")
        else:
            report("Conflict detection endpoint works", False, f"status={r_detect.status_code}")

        # ==================================================================
        # TEST 8: Non-overlapping rules should both be active
        # ==================================================================
        print("\n[8] Non-overlapping rules should BOTH be active")
        await delete_all_rules(client)
        no_overlap_a = {
            "name": "AmountHigh", "description": "d", "group": "nooverlap",
            "priority": 1, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "amount", "op": ">", "value": 10000},
            "action": "block_transaction",
        }
        no_overlap_b = {
            "name": "CountryBlock", "description": "d", "group": "nooverlap",
            "priority": 2, "enabled": True,
            "condition_dsl": {"type": "condition", "field": "country", "op": "==", "value": "CN"},
            "action": "flag_suspicious",
        }
        r_noa = await client.post(f"{BASE_URL}/rules", json=no_overlap_a, headers=headers())
        r_nob = await client.post(f"{BASE_URL}/rules", json=no_overlap_b, headers=headers())
        report("Non-overlapping rule A created", r_noa.status_code == 200)
        report("Non-overlapping rule B created", r_nob.status_code == 200)

        # Cleanup
        print("\n[cleanup] Removing test rules...")
        await delete_all_rules(client)

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print(f"\n{'='*65}")
    print("SUMMARY")
    print(f"{'='*65}")
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    print(f"  {PASS} Passed: {passed}")
    print(f"  {FAIL} Failed: {failed}")
    if failed:
        print(f"\n  Failed tests:")
        for name, p, detail in results:
            if not p:
                print(f"    {FAIL} {name}: {detail}")
    print(f"{'='*65}\n")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_verification())
    sys.exit(0 if ok else 1)
