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


def generate_complex_rules(count: int = 50) -> List[Dict]:
    """Generate complex rules for performance testing."""
    rules = []
    
    groups = ["fraud_detection", "compliance", "risk_management", "aml", "transaction_monitoring"]
    actions = ["flag_suspicious", "block_transaction", "require_review", "send_alert", "escalate"]
    
    for i in range(count):
        rule = {
            "name": f"Complex_Rule_{i+1:03d}_{random.randint(1000, 9999)}",
            "description": f"Complex test rule #{i+1} with nested conditions for performance testing",
            "group": random.choice(groups),
            "priority": random.randint(1, 100),
            "enabled": True,
            "condition_dsl": generate_nested_condition(depth=random.randint(2, 4), breadth=random.randint(2, 4)),
            "action": random.choice(actions)
        }
        rules.append(rule)
    
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
    if response.status_code in [200, 201, 207]:
        return response.json()
    else:
        print(f"Bulk create failed: {response.status_code} - {response.text}")
        return None


async def delete_all_rules(client: httpx.AsyncClient):
    """Delete all existing rules."""
    response = await client.get(f"{BASE_URL}/rules", headers=get_headers())
    if response.status_code == 200:
        rules = response.json()
        for rule in rules:
            await client.delete(f"{BASE_URL}/rules/{rule['id']}", headers=get_headers())
        print(f"Deleted {len(rules)} existing rules")


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
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Clear existing rules
        print("\n[2] Clearing existing rules...")
        await delete_all_rules(client)
        print("✓ Existing rules cleared")
        
        # Generate 50 complex rules
        print("\n[3] Generating 50 complex rules...")
        complex_rules = generate_complex_rules(50)
        print(f"✓ Generated {len(complex_rules)} complex rules")
        
        # TEST 1: Fast creation (skip conflict check)
        print("\n[4] Creating rules WITH skip_conflict_check=true (FAST MODE)...")
        start_time = time.time()
        created_count = 0
        for i, rule in enumerate(complex_rules):
            result = await create_rule_fast(client, rule)
            if result:
                created_count += 1
            if (i + 1) % 10 == 0:
                print(f"   Created {i + 1}/{len(complex_rules)} rules...")
        
        fast_creation_time = time.time() - start_time
        print(f"✓ Created {created_count} rules in {fast_creation_time:.2f} seconds")
        print(f"  Average: {fast_creation_time/max(created_count,1)*1000:.2f}ms per rule")
        
        # Clear for bulk test
        await delete_all_rules(client)
        
        # TEST 2: Bulk creation
        print("\n[5] Creating rules using BULK endpoint...")
        start_time = time.time()
        bulk_result = await bulk_create_rules(client, complex_rules)
        bulk_creation_time = time.time() - start_time
        
        if bulk_result:
            if isinstance(bulk_result, list):
                bulk_count = len(bulk_result)
            else:
                bulk_count = len(bulk_result.get("created", bulk_result))
            print(f"✓ Bulk created {bulk_count} rules in {bulk_creation_time:.2f} seconds")
            print(f"  Average: {bulk_creation_time/max(bulk_count,1)*1000:.2f}ms per rule")
        else:
            bulk_count = 0
            print("  Bulk creation failed")
        
        # Clear for normal test
        await delete_all_rules(client)
        
        # TEST 3: Normal creation (with conflict check) - just 10 rules
        print("\n[6] Creating 10 rules WITH conflict check (NORMAL MODE)...")
        normal_rules = complex_rules[:10]
        start_time = time.time()
        normal_count = 0
        for rule in normal_rules:
            result = await create_rule(client, rule)
            if result:
                normal_count += 1
        
        normal_creation_time = time.time() - start_time
        print(f"✓ Created {normal_count} rules in {normal_creation_time:.2f} seconds")
        print(f"  Average: {normal_creation_time/max(normal_count,1)*1000:.2f}ms per rule")
        
        # Now create the rest with fast mode
        print("\n   Creating remaining 40 rules with fast mode...")
        remaining_rules = complex_rules[10:]
        fast_remaining_count = 0
        for rule in remaining_rules:
            result = await create_rule_fast(client, rule)
            if result:
                fast_remaining_count += 1
        
        total_rules_created = normal_count + fast_remaining_count
        
        # Create 5 conflicting rules
        print("\n[7] Creating 5 conflicting rules...")
        conflicting_rules = generate_conflicting_rules()
        for rule in conflicting_rules:
            result = await create_rule_fast(client, rule)
            if result:
                print(f"   ✓ Created: {rule['name']}")
        
        # Check total rules
        response = await client.get(f"{BASE_URL}/rules", headers=get_headers())
        if response.status_code == 200:
            total_rules = len(response.json())
            print(f"\n✓ Total rules in system: {total_rules}")
        else:
            total_rules = 0
        
        # Check for conflicts
        print("\n[8] Checking for conflicts...")
        start_time = time.time()
        conflicts = await check_conflicts(client)
        conflict_check_time = time.time() - start_time
        
        if conflicts:
            print(f"✓ Conflict check completed in {conflict_check_time*1000:.2f}ms")
            if isinstance(conflicts, dict):
                if conflicts.get("conflicts"):
                    print(f"\n⚠️  Found {len(conflicts['conflicts'])} conflicts:")
                    for i, conflict in enumerate(conflicts["conflicts"][:10]):  # Show first 10
                        print(f"   {i+1}. {conflict}")
                else:
                    print("   No conflicts detected")
            elif isinstance(conflicts, list):
                print(f"\n⚠️  Found {len(conflicts)} conflicts:")
                for i, conflict in enumerate(conflicts[:10]):
                    print(f"   {i+1}. {conflict}")
        
        # Performance test: Submit events
        print("\n[9] Performance test: Submitting events to queue...")
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
            print("\n[8] Bulk submission test (100 events)...")
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
            print("\n[10] Skipping bulk test (Redis not available)")
        
        # Summary
        print("\n" + "=" * 60)
        print("PERFORMANCE TEST SUMMARY")
        print("=" * 60)
        print(f"Total Rules:           {total_rules}")
        print("\nRule Creation Performance:")
        print(f"  Fast Mode (50 rules):    {fast_creation_time:.2f}s ({fast_creation_time/max(created_count,1)*1000:.2f}ms avg)")
        print(f"  Bulk Mode (50 rules):    {bulk_creation_time:.2f}s ({bulk_creation_time/max(bulk_count,1)*1000:.2f}ms avg)")
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
