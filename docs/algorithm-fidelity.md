# Algorithm Fidelity: PHREAK vs the Reference Evaluator

**Prerequisites:** [The FluxRules Engine](engine-comparison.md).

---

FluxRules ships one production engine (PHREAK). To guard against defects in shared
code, the test suite checks PHREAK against an independent, dependency-free
**reference evaluator** (`fluxrules.services.reference_evaluator.ReferenceEvaluator`).
Because the two implementations share no matching code, agreeing on results is
strong evidence of correctness.

## Verification approach

**Test dataset:** cross_border_payment_risk_triage (3 facts, shared use case)

**Test rules:** All 31 example rules with varying complexity:
- Simple conditions (1 field)
- Complex AND/OR logic
- NOT operators
- Nested groups

**Verification method:**
1. Load the same ruleset into PHREAK and the reference evaluator
2. Evaluate identical facts
3. Compare `fired_rules` and `actions`
4. Assert complete parity

The same harness also compares PHREAK's **stateless** and **streaming** modes to
confirm a fact fires the same rules on first sight in either mode.

## Results

✅ **COMPLETE PARITY** — PHREAK matches the reference evaluator on all test cases.

| Test Case | PHREAK | Reference | Match |
|-----------|--------|-----------|-------|
| Simple condition | ✅ | ✅ | ✅ |
| AND groups | ✅ | ✅ | ✅ |
| OR groups | ✅ | ✅ | ✅ |
| NOT operator | ✅ | ✅ | ✅ |
| Nested groups | ✅ | ✅ | ✅ |
| Multiple rules | ✅ | ✅ | ✅ |

**Conclusion:** PHREAK's optimized matching is semantically equivalent to the
naive reference evaluator across the supported condition surface.

---

## Next Steps

- **The FluxRules Engine** — See [The FluxRules Engine](engine-comparison.md) for evaluation modes
- **Benchmarks** — See [Benchmarks](benchmarks.md) for latency/throughput data
