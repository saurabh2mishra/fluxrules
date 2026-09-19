"""Detailed performance analysis: baseline vs optimized engine."""

import sys
import time

sys.path.insert(0, "src")
sys.path.insert(0, "tests/performance")

from generators import and_heavy_rules

from fluxrules.engine.phreak import PhreakEngine

print("=" * 70)
print("PERFORMANCE ANALYSIS: Baseline vs Optimized")
print("=" * 70)

# Test 1: Load Time
print("\n1. RULE LOADING (lower is better)")
print("-" * 70)

for n_rules in [1_000, 5_000, 10_000]:
    # Create industry-realistic rules with 8 AND-ed conditions
    rules = and_heavy_rules(n_rules, n_conditions=8)
    engine = PhreakEngine()

    start = time.perf_counter()
    engine.load_rules(rules)
    elapsed_ms = (time.perf_counter() - start) * 1000

    segments_count = len(engine.segment_network)
    print(f"   {n_rules:,} rules → {segments_count:,} segments: {elapsed_ms:>8.2f}ms")

# Test 2: Single Fact Evaluation (discovery + rule eval)
print("\n2. SINGLE FACT EVALUATION (lower is better)")
print("-" * 70)

for n_rules in [100, 500, 1_000, 5_000]:
    # Create industry-realistic rules with 8 AND-ed conditions
    rules = and_heavy_rules(n_rules, n_conditions=8)
    engine = PhreakEngine()
    engine.load_rules(rules)

    fact = {"amount": 500}
    times = []
    for _ in range(10):
        start = time.perf_counter()
        result = engine.evaluate(fact)
        times.append((time.perf_counter() - start) * 1000)

    avg_ms = sum(times) / len(times)
    min_ms = min(times)
    max_ms = max(times)
    fired = len(result.fired_rules)

    print(
        f"   {n_rules:,} rules, {fired} fired: {avg_ms:>7.2f}ms avg (min: {min_ms:.2f}, max: {max_ms:.2f})"
    )

# Test 3: Batch Evaluation (1K facts)
print("\n3. BATCH EVALUATION - 1,000 Facts (lower is better)")
print("-" * 70)

for n_rules in [100, 500, 1_000]:
    # Create industry-realistic rules with 8 AND-ed conditions
    rules = and_heavy_rules(n_rules, n_conditions=8)
    engine = PhreakEngine()
    engine.load_rules(rules)

    facts = [{"amount": i * 10 % 500} for i in range(1_000)]

    start = time.perf_counter()
    total_fired = 0
    for fact in facts:
        result = engine.evaluate(fact)
        total_fired += len(result.fired_rules)
    elapsed_sec = time.perf_counter() - start

    throughput = 1_000 / elapsed_sec
    total_checks = 1_000 * n_rules  # fact × rule combinations
    ops_per_sec = total_checks / elapsed_sec

    print(
        f"   {n_rules:,} rules: {throughput:>6.0f} facts/sec ({ops_per_sec:,.0f} rule checks/sec)"
    )

# Test 4: High-Cardinality Evaluation (small fact set, large rule set)
print("\n4. HIGH-CARDINALITY (50k rules with 15 conditions each)")
print("-" * 70)

n_rules = 50_000
print(f"   Loading {n_rules:,} rules...")
# Create industry-realistic rules with 15 AND-ed conditions
rules = and_heavy_rules(n_rules, n_conditions=15)
engine = PhreakEngine()
start = time.perf_counter()
engine.load_rules(rules)
load_time = (time.perf_counter() - start) * 1000
print(f"   Load time: {load_time:.1f}ms")

# Evaluate 100 times with different facts
fact_templates = [
    {f"field_{i}": 1000 for i in range(15)},  # All 15 fields high → high match
    {f"field_{i}": 5 for i in range(15)},  # All 15 fields low → low match
    {f"field_{i}": 1000 if i % 2 == 0 else 5 for i in range(15)},  # Mixed
]

for template in fact_templates:
    times = []
    for _ in range(100):
        start = time.perf_counter()
        result = engine.evaluate(template)
        times.append((time.perf_counter() - start) * 1000)

    avg_ms = sum(times) / len(times)
    fired = len(result.fired_rules)
    print(f"   Fact {template} → {fired:,} fired: {avg_ms:.3f}ms avg")

# Test 5: Parallel vs Sequential Threshold
print("\n5. PARALLEL EVALUATION THRESHOLD (500 rules, 8 conditions each)")
print("-" * 70)

# Create industry-realistic rules with 8 AND-ed conditions
rules = and_heavy_rules(500, n_conditions=8)
engine = PhreakEngine()
engine.load_rules(rules)

fact = {f"field_{i}": 500 for i in range(8)}  # Provides values for 8 fields
times = []
for _ in range(50):
    start = time.perf_counter()
    result = engine.evaluate(fact)
    times.append((time.perf_counter() - start) * 1000)

avg_ms = sum(times) / len(times)
print(f"   500 matched rules: {avg_ms:.3f}ms avg (parallel path active)")
print("   (Sequential threshold = 50, so parallel used here)")

print("\n" + "=" * 70)
print("NOTES:")
print("- Optimizations: condition caching, cardinality fast-reject, parallel eval")
print("- Parallel threshold = 50 matched rules (config option)")
print("- ThreadPoolExecutor with 4 workers for high-rule-count evals")
print("=" * 70)
