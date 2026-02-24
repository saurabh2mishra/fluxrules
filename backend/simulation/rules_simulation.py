import asyncio
import httpx
import json
import time
import random
from typing import List, Dict, Any

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"

# Store auth token
auth_token = None


async def login() -> str:
    """Login and get auth token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/auth/token",
            data={"username": USERNAME, "password": PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None


def get_headers():
    """Get auth headers."""
    return {"Authorization": f"Bearer {auth_token}"}


# Complex condition generators
def generate_nested_condition(depth: int = 3, breadth: int = 3) -> Dict:
    """Generate a nested condition tree."""
    if depth <= 0:
        # Leaf condition
        fields = ["amount", "transaction_type", "country", "user_id", "risk_score", 
                  "account_age", "velocity", "ip_address", "device_id", "merchant_category"]
        operators = ["==", "!=", ">", "<", ">=", "<=", "in", "contains"]
        field = random.choice(fields)
        op = random.choice(operators)
        
        if field in ["amount", "risk_score", "account_age", "velocity"]:
            value = random.randint(100, 100000) if field == "amount" else random.randint(1, 100)
        elif field in ["country"]:
            value = random.choice(["US", "UK", "CA", "AU", "DE", "FR", "JP", "CN", "IN", "BR"])
        elif field in ["transaction_type"]:
            value = random.choice(["transfer", "purchase", "withdrawal", "deposit", "refund"])
        elif field in ["merchant_category"]:
            value = random.choice(["retail", "travel", "entertainment", "gambling", "crypto"])
        else:
            value = f"value_{random.randint(1000, 9999)}"
        
        return {
            "type": "condition",
            "field": field,
            "op": op,
            "value": value
        }
    else:
        # Group with children
        return {
            "type": "group",
            "op": random.choice(["AND", "OR"]),
            "children": [generate_nested_condition(depth - 1, breadth) for _ in range(random.randint(2, breadth))]
        }


def generate_simple_rules(count: int = 1000) -> List[Dict]:
    """Generate simple rules with unique logical names."""
    rules = []
    for i in range(count):
        # Use index in name to guarantee uniqueness
        seq = i + 1
        field = random.choice([
            "amount", "country", "transaction_type", "account_age", "risk_score"
        ])
        if field == "amount":
            value = random.randint(100, 10000)
            name = f"Amount_Threshold_{value}_R{seq}"
            condition = {"type": "condition", "field": "amount", "op": ">", "value": value}
        elif field == "country":
            value = random.choice(["US", "UK", "FR", "DE", "CA", "AU"])
            name = f"Country_Block_{value}_R{seq}"
            condition = {"type": "condition", "field": "country", "op": "==", "value": value}
        elif field == "transaction_type":
            value = random.choice(["transfer", "purchase", "withdrawal", "deposit"])
            name = f"TxnType_{value}_R{seq}"
            condition = {"type": "condition", "field": "transaction_type", "op": "==", "value": value}
        elif field == "account_age":
            value = random.randint(1, 100)
            name = f"AcctAge_Over_{value}_R{seq}"
            condition = {"type": "condition", "field": "account_age", "op": ">", "value": value}
        else:
            value = random.randint(1, 100)
            name = f"RiskScore_Over_{value}_R{seq}"
            condition = {"type": "condition", "field": "risk_score", "op": ">", "value": value}
        rules.append({
            "name": name,
            "description": f"Simple rule #{seq} for {field} threshold",
            "group": "simple",
            "priority": random.randint(1, 100),
            "enabled": True,
            "condition_dsl": condition,
            "action": random.choice(["flag_suspicious", "block_transaction", "require_review"])
        })
    return rules


def generate_complex_rules(count: int = 50, prefix: str = "HighRisk_MultiField") -> List[Dict]:
    """Generate complex rules with unique logical names."""
    rules = []
    for i in range(count):
        name = f"{prefix}_{i+1}_Rule"
        condition = {
            "type": "group",
            "op": random.choice(["AND", "OR"]),
            "children": [
                {"type": "condition", "field": "amount", "op": ">", "value": random.randint(5000, 50000)},
                {"type": "condition", "field": "risk_score", "op": ">", "value": random.randint(50, 100)},
                {"type": "condition", "field": "country", "op": "==", "value": random.choice(["US", "UK", "FR", "DE"])}
            ]
        }
        rules.append({
            "name": name,
            "description": "Complex rule for high risk multi-field checks",
            "group": "complex",
            "priority": random.randint(1, 100),
            "enabled": True,
            "condition_dsl": condition,
            "action": random.choice(["block_transaction", "escalate", "send_alert"])
        })
    return rules


def generate_conflicting_rules() -> List[Dict]:
    """Generate 5 rules that will conflict with each other."""
    # These rules intentionally share the same fields and have overlapping conditions
    conflicting_rules = [
        {
            "name": "Conflict_Rule_A_HighAmount",
            "description": "Flags transactions over 10000",
            "group": "fraud_detection",
            "priority": 10,
            "enabled": True,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 10000},
                    {"type": "condition", "field": "country", "op": "==", "value": "US"}
                ]
            },
            "action": "flag_suspicious"
        },
        {
            "name": "Conflict_Rule_B_HighAmount_Block",
            "description": "Blocks transactions over 10000 - CONFLICTS with Rule A",
            "group": "fraud_detection",
            "priority": 20,
            "enabled": True,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 10000},
                    {"type": "condition", "field": "country", "op": "==", "value": "US"}
                ]
            },
            "action": "block_transaction"  # Different action = potential conflict
        },
        {
            "name": "Conflict_Rule_C_AmountRange",
            "description": "Overlaps with A and B on amount range",
            "group": "fraud_detection",
            "priority": 15,
            "enabled": True,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 5000},
                    {"type": "condition", "field": "amount", "op": "<", "value": 50000},
                    {"type": "condition", "field": "country", "op": "==", "value": "US"}
                ]
            },
            "action": "require_review"
        },
        {
            "name": "Conflict_Rule_D_SameConditionDifferentAction",
            "description": "Exact same condition as A but different action",
            "group": "compliance",
            "priority": 5,
            "enabled": True,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 10000},
                    {"type": "condition", "field": "country", "op": "==", "value": "US"}
                ]
            },
            "action": "send_alert"
        },
        {
            "name": "Conflict_Rule_E_SubsetCondition",
            "description": "Subset of conditions - will always fire when A fires",
            "group": "fraud_detection",
            "priority": 25,
            "enabled": True,
            "condition_dsl": {
                "type": "group",
                "op": "AND",
                "children": [
                    {"type": "condition", "field": "amount", "op": ">", "value": 10000}
                ]
            },
            "action": "escalate"
        }
    ]
    return conflicting_rules


async def create_rule(client: httpx.AsyncClient, rule: Dict) -> Dict:
    """Create a single rule."""
    response = await client.post(
        f"{BASE_URL}/rules",
        json=rule,
        headers=get_headers()
    )
    if response.status_code in [200, 201]:
        return response.json()
    else:
        print(f"Failed to create rule {rule['name']}: {response.status_code} - {response.text}")
        return None


async def create_rule_fast(client: httpx.AsyncClient, rule: Dict) -> Dict:
    """Create a single rule with skip_conflict_check for faster creation."""
    response = await client.post(
        f"{BASE_URL}/rules?skip_conflict_check=true",
        json=rule,
        headers=get_headers()
    )
    if response.status_code in [200, 201]:
        return response.json()
    else:
        print(f"Failed to create rule {rule['name']}: {response.status_code} - {response.text}")
        return None


async def bulk_create_rules(client: httpx.AsyncClient, rules: List[Dict]) -> Dict:
    """Create multiple rules in a single request."""
    response = await client.post(
        f"{BASE_URL}/rules/bulk",
        json=rules,
        headers=get_headers(),
        timeout=120.0  # Longer timeout for bulk
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return data
    elif response.status_code == 207:
        # FastAPI wraps HTTPException detail: {"detail": {"created": [...], "errors": [...]}}
        detail = data.get("detail", data)
        created = detail.get("created", [])
        errors = detail.get("errors", [])
        if errors:
            print(f"  ⚠️  Bulk partial: {len(created)} created, {len(errors)} failed")
            for err in errors[:5]:
                print(f"     - [{err.get('index')}] {err.get('rule_name')}: {err.get('error', '')[:80]}")
        return created  # Return the list of successfully created rules
    else:
        print(f"Bulk create failed: {response.status_code} - {response.text[:200]}")
        return None


async def delete_all_rules(client: httpx.AsyncClient):
    """Delete all existing rules."""
    deleted_total = 0
    while True:
        response = await client.get(f"{BASE_URL}/rules?limit=200", headers=get_headers())
        if response.status_code == 200:
            rules = response.json()
            if not rules:
                break
            for rule in rules:
                await client.delete(f"{BASE_URL}/rules/{rule['id']}", headers=get_headers())
            deleted_total += len(rules)
        else:
            break
    print(f"Deleted {deleted_total} existing rules")


async def check_conflicts(client: httpx.AsyncClient):
    """Check for conflicts in the rules."""
    response = await client.get(f"{BASE_URL}/rules/conflicts/detect", headers=get_headers())
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to check conflicts: {response.status_code} - {response.text}")
        return None


async def evaluate_event(client: httpx.AsyncClient, event: Dict) -> Dict:
    """Evaluate an event against all rules."""
    # Wrap the event data in the expected schema
    event_payload = {
        "event_type": "transaction",
        "data": event,
        "metadata": {}
    }
    try:
        response = await client.post(
            f"{BASE_URL}/events",
            json=event_payload,
            headers=get_headers(),
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.status_code}
    except Exception as e:
        return {"error": str(e)}


async def run_performance_test():
    """Run the full performance test."""
    global auth_token
    
    print("=" * 60)
    print("RULES ENGINE PERFORMANCE TEST")
    print("=" * 60)
    
    # Login
    print("\n[1] Logging in...")
    auth_token = await login()
    if not auth_token:
        print("Failed to login. Make sure the server is running and credentials are correct.")
        return
    print("✓ Login successful")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Clear existing rules
        print("\n[2] Clearing existing rules...")
        await delete_all_rules(client)
        print("✓ Existing rules cleared")
        
        # Generate and create simple rules in batches
        print("\n[3] Generating 1000 simple rules...")
        simple_rules = generate_simple_rules(1000)
        print(f"✓ Generated {len(simple_rules)} simple rules")
        print("    Creating simple rules (bulk, batches of 100)...")
        batch_size = 100
        simple_created = 0
        for batch_start in range(0, len(simple_rules), batch_size):
            batch = simple_rules[batch_start:batch_start + batch_size]
            result = await bulk_create_rules(client, batch)
            if result:
                if isinstance(result, list):
                    simple_created += len(result)
                else:
                    simple_created += len(result.get("created", []))
            print(f"    ... batch {batch_start // batch_size + 1}/{(len(simple_rules) + batch_size - 1) // batch_size} done ({simple_created} total)")
        print(f"✓ Simple rules created: {simple_created}")
        
        # Generate and create complex rules
        print("\n[4] Generating 50 complex rules...")
        complex_rules = generate_complex_rules(50)
        print(f"✓ Generated {len(complex_rules)} complex rules")
        print("    Creating complex rules (bulk)...")
        result = await bulk_create_rules(client, complex_rules)
        complex_created = 0
        if result:
            if isinstance(result, list):
                complex_created = len(result)
            else:
                complex_created = len(result.get("created", []))
        print(f"✓ Complex rules created: {complex_created}")
        
        # Verify total after initial creation of 1000 simple + 50 complex
        response = await client.get(f"{BASE_URL}/rules?limit=2000", headers=get_headers())
        if response.status_code == 200:
            initial_total = len(response.json())
            print(f"\n✓ Total rules after initial load: {initial_total}")
        else:
            initial_total = 0

        # Create conflict rules and capture rejected
        print("\n[5] Creating conflict rules...")
        conflict_rules = generate_conflicting_rules()
        rejected_conflicts = []
        for rule in conflict_rules:
            result = await create_rule(client, rule)
            if not result:
                rejected_conflicts.append(rule)
                print(f"✗ Rejected: {rule['name']}")
            else:
                print(f"✓ Created: {rule['name']}")
        if rejected_conflicts:
            print("\n⚠️ Rejected Conflict Rules (for business review):")
            for rule in rejected_conflicts:
                print(f"   - {rule['name']}: {rule['description']}")

        # Provide delete/flush routine for rejected rules
        print("\n[6] Deleting/flushing rejected conflict rules...")
        for rule in rejected_conflicts:
            response = await client.get(f"{BASE_URL}/rules?limit=2000", headers=get_headers())
            if response.status_code == 200:
                rules = response.json()
                for r in rules:
                    if r['name'] == rule['name']:
                        await client.delete(f"{BASE_URL}/rules/{r['id']}", headers=get_headers())
                        print(f"   Deleted: {r['name']}")
        print("✓ Rejected conflict rules flushed")

        # ------------------------------------------------------------------
        # BENCHMARK TESTS (use small separate batches, then clean them up)
        # ------------------------------------------------------------------

        # TEST 1: Fast creation benchmark (skip conflict check) — 20 extra rules
        print("\n[7] BENCHMARK: Fast creation mode (20 rules, skip_conflict_check=true)...")
        benchmark_fast_rules = generate_complex_rules(20, prefix="BenchFast")
        start_time = time.time()
        bench_fast_ids = []
        for i, rule in enumerate(benchmark_fast_rules):
            result = await create_rule_fast(client, rule)
            if result:
                bench_fast_ids.append(result["id"])
        fast_creation_time = time.time() - start_time
        fast_created_count = len(bench_fast_ids)
        print(f"✓ Created {fast_created_count} rules in {fast_creation_time:.2f} seconds")
        print(f"  Average: {fast_creation_time/max(fast_created_count,1)*1000:.2f}ms per rule")
        # Clean up benchmark rules
        for rid in bench_fast_ids:
            await client.delete(f"{BASE_URL}/rules/{rid}", headers=get_headers())

        # TEST 2: Bulk creation benchmark — 20 extra rules
        print("\n[8] BENCHMARK: Bulk creation mode (20 rules)...")
        benchmark_bulk_rules = generate_complex_rules(20, prefix="BenchBulk")
        start_time = time.time()
        bulk_result = await bulk_create_rules(client, benchmark_bulk_rules)
        bulk_creation_time = time.time() - start_time
        bench_bulk_ids = []
        if bulk_result:
            if isinstance(bulk_result, list):
                bulk_count = len(bulk_result)
                bench_bulk_ids = [r["id"] for r in bulk_result]
            else:
                created_list = bulk_result.get("created", [])
                bulk_count = len(created_list)
                bench_bulk_ids = [r["id"] for r in created_list]
            print(f"✓ Bulk created {bulk_count} rules in {bulk_creation_time:.2f} seconds")
            print(f"  Average: {bulk_creation_time/max(bulk_count,1)*1000:.2f}ms per rule")
        else:
            bulk_count = 0
            print("  Bulk creation failed")
        # Clean up benchmark rules
        for rid in bench_bulk_ids:
            await client.delete(f"{BASE_URL}/rules/{rid}", headers=get_headers())

        # TEST 3: Normal creation benchmark (with conflict check) — 10 extra rules
        print("\n[9] BENCHMARK: Normal creation mode (10 rules, with conflict check)...")
        benchmark_normal_rules = generate_complex_rules(10, prefix="BenchNormal")
        start_time = time.time()
        bench_normal_ids = []
        for rule in benchmark_normal_rules:
            result = await create_rule(client, rule)
            if result:
                bench_normal_ids.append(result["id"])
        normal_creation_time = time.time() - start_time
        normal_count = len(bench_normal_ids)
        print(f"✓ Created {normal_count} rules in {normal_creation_time:.2f} seconds")
        print(f"  Average: {normal_creation_time/max(normal_count,1)*1000:.2f}ms per rule")
        # Clean up benchmark rules
        for rid in bench_normal_ids:
            await client.delete(f"{BASE_URL}/rules/{rid}", headers=get_headers())

        # ------------------------------------------------------------------
        # FINAL STATE: All 1000 simple + 50 complex + accepted conflict rules remain
        # ------------------------------------------------------------------

        # Check total rules (should be >= 1050)
        response = await client.get(f"{BASE_URL}/rules?limit=2000", headers=get_headers())
        if response.status_code == 200:
            total_rules = len(response.json())
            print(f"\n✓ Total rules in system: {total_rules}")
        else:
            total_rules = 0

        # Check for conflicts
        print("\n[10] Checking for conflicts...")
        start_time = time.time()
        conflicts = await check_conflicts(client)
        conflict_check_time = time.time() - start_time

        if conflicts:
            print(f"✓ Conflict check completed in {conflict_check_time*1000:.2f}ms")
            if isinstance(conflicts, dict):
                if conflicts.get("conflicts"):
                    print(f"\n⚠️  Found {len(conflicts['conflicts'])} conflicts:")
                    for i, conflict in enumerate(conflicts["conflicts"][:10]):
                        print(f"   {i+1}. {conflict}")
                else:
                    print("   No conflicts detected")
            elif isinstance(conflicts, list):
                print(f"\n⚠️  Found {len(conflicts)} conflicts:")
                for i, conflict in enumerate(conflicts[:10]):
                    print(f"   {i+1}. {conflict}")

        # Performance test: Submit events
        print("\n[11] Performance test: Submitting events to queue...")
        print("    (Note: Requires Redis to be running)")
        test_events = [
            {"amount": 15000, "country": "US", "transaction_type": "transfer", "risk_score": 75},
            {"amount": 500, "country": "UK", "transaction_type": "purchase", "risk_score": 10},
            {"amount": 50000, "country": "US", "transaction_type": "withdrawal", "risk_score": 90},
            {"amount": 1000, "country": "CA", "transaction_type": "deposit", "risk_score": 5},
            {"amount": 25000, "country": "US", "transaction_type": "transfer", "merchant_category": "crypto"},
        ]
        
        evaluation_times = []
        events_success = 0
        events_failed = 0
        for i, event in enumerate(test_events):
            start_time = time.time()
            result = await evaluate_event(client, event)
            eval_time = time.time() - start_time
            evaluation_times.append(eval_time)
            
            if result and "error" not in result:
                events_success += 1
                status = result.get("status", "unknown")
                event_id = result.get("event_id", "N/A")
                print(f"   Event {i+1}: {eval_time*1000:.2f}ms - Status: {status} (ID: {event_id[:8]}...)")
            else:
                events_failed += 1
        
        if events_failed > 0:
            print(f"   ⚠️  {events_failed}/{len(test_events)} events failed (Redis may not be running)")
        
        avg_eval_time = sum(evaluation_times) / len(evaluation_times) if evaluation_times else 0
        if events_success > 0:
            print(f"\n✓ Average submission time: {avg_eval_time*1000:.2f}ms")
            print(f"  Min: {min(evaluation_times)*1000:.2f}ms")
            print(f"  Max: {max(evaluation_times)*1000:.2f}ms")
        
        # Bulk evaluation test (only if events are working)
        bulk_time = 0
        if events_success > 0:
            print("\n[12] Bulk submission test (100 events)...")
            bulk_events = []
            for _ in range(100):
                bulk_events.append({
                    "amount": random.randint(100, 100000),
                    "country": random.choice(["US", "UK", "CA", "AU", "DE"]),
                    "transaction_type": random.choice(["transfer", "purchase", "withdrawal"]),
                    "risk_score": random.randint(1, 100),
                    "user_id": f"user_{random.randint(1000, 9999)}"
                })
            
            start_time = time.time()
            for event in bulk_events:
                await evaluate_event(client, event)
            bulk_time = time.time() - start_time
            
            print(f"✓ Submitted 100 events in {bulk_time:.2f} seconds")
            print(f"  Average: {bulk_time/100*1000:.2f}ms per event")
            print(f"  Throughput: {100/bulk_time:.1f} events/second")
        else:
            print("\n[13] Skipping bulk test (Redis not available)")
        
        # Summary
        print("\n" + "=" * 60)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 60)
        print(f"Total Rules:           {total_rules} (target: ≥1050)")
        print("\nRule Creation Benchmarks:")
        print(f"  Fast Mode (20 rules):    {fast_creation_time:.2f}s ({fast_creation_time/max(fast_created_count,1)*1000:.2f}ms avg)")
        print(f"  Bulk Mode (20 rules):    {bulk_creation_time:.2f}s ({bulk_creation_time/max(bulk_count,1)*1000:.2f}ms avg)")
        print(f"  Normal Mode (10 rules):  {normal_creation_time:.2f}s ({normal_creation_time/max(normal_count,1)*1000:.2f}ms avg)")
        print(f"\nConflict Check Time:   {conflict_check_time*1000:.2f}ms")
        if events_success > 0:
            print(f"Event Submission:      {avg_eval_time*1000:.2f}ms avg")
            if bulk_time > 0:
                print(f"Bulk Throughput:       {100/bulk_time:.1f} events/second")
        else:
            print(f"Event Submission:      N/A (Redis not available)")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_performance_test())
