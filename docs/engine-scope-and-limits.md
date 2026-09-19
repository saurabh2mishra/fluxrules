# Engine Scope and Limits

**Prerequisites:** [The FluxRules Engine](engine-comparison.md).

---

Documented constraints and capabilities of FluxRules engines.

## Single-fact evaluation

**Scope:** Both engines evaluate one fact dict per call.

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
# Each evaluate() is independent
result1 = engine.evaluate({"amount": 5000})
result2 = engine.evaluate({"amount": 7500})
# result1 and result2 have no shared state
```

**Limitation:** Engines do not join facts, aggregate over collections, or correlate across time.

**Workaround:** Pre-aggregate facts upstream, then pass combined dict to evaluate().

For a deployment where unsupported cross-fact or temporal rule shapes must fail
at startup instead of logging a warning, enable the strict guardrail:

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine(strict_scope=True)
engine.load_rules(
    [
        Rule(
            name="amount_check",
            condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
            action="review",
            persist=False,
        )
    ]
)
```

Use the separate [Cross-Fact Rules](cross-fact-rules.md) engine when the rule
semantics genuinely require joins, windows, or truth maintenance.

## Rule complexity

**Scope:** DSL supports arbitrary nesting of AND/OR/NOT operators.

**Limits enforced by the code:**
- Rules: default cap of **50,000** per engine (`GlobalRuleRepository`); configurable via `PhreakEngine(max_rules=...)`. Exceeding the cap raises `ValueError("Repository full")`.
- Conditions per rule and nesting depth: no fixed cap in the engine; arbitrary AND/OR/NOT nesting is supported (deep nesting is exercised in the test suite). Depth is ultimately bounded by Python's recursion limit.

**Performance:** Evaluation time scales roughly with rule count and condition complexity; measure your own workload (see [Load Testing](load-testing.md)).

### Capacity and selectivity guidance

The default per-engine capacity is 50,000 rules. Raising `max_rules` only
removes the repository guard; it does not make a low-selectivity workload
cheap. PHREAK first reduces candidates with field presence and the alpha
prefilter, then evaluates the remaining candidates. Rules sharing few indexed
predicates or matching a hot field can therefore approach rule-count work per
fact.

For a production rollout, load the complete ruleset once, measure a
representative fact sample, and record the candidate and latency metrics before
choosing a worker count:

```python
from fluxrules.engine.phreak import PhreakEngine
from fluxrules import Rule

rules = [
    Rule(
        name="amount_check",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
        action="review",
        persist=False,
    )
]
representative_facts = [{"amount": 1500}, {"amount": 50}]

engine = PhreakEngine(max_rules=50000, enable_metrics=True)
engine.load_rules(rules)
for fact in representative_facts:
    engine.evaluate(fact)

metrics = engine.get_observability_metrics()
print(
    metrics["rules_loaded"],
    metrics["candidates_per_fact_out"],
    metrics["alpha_prune_ratio"],
    metrics["eval_latency_ms_p95"],
)
```

Treat a low `alpha_prune_ratio`, high `candidates_per_fact_out`, or rising
`eval_latency_ms` as a signal to split rulesets, improve selective predicates,
or scale stateless workers. Do not infer capacity from the 50,000-rule limit
alone.

## Fact size

**Scope:** Facts are flat dicts after the flattening pipeline.

**Limits enforced by the code:**
- Fact keys: no fixed limit in the engine (bounded by available memory).
- Value size: large strings/numbers supported.
- Nested depth: `Flatten()` converts nested dicts to dot notation up to `max_depth=100` (default) and raises `ValueError` beyond that.

## Working memory

**Scope:** PHREAK has optional working memory for fact storage.

**Limits:**
- Stateless mode: No persistent network overhead, working memory is optional
- Streaming mode: Working memory persists across calls

**Working memory size:** Limited by available RAM. No fixed limit.

**Use case:** Store intermediate facts during multi-step workflows with sessions.

## Streaming mode

**Scope:** PhreakEngine supports streaming mode via `streaming_mode=True`.

**Limitation:** Streaming returns deltas (changes since last evaluation), not absolute matches.

**Requirement:** Sticky routing (same stream → same engine instance).

Streaming state is local to one `PhreakEngine` instance. Do not send one
ordered stream through ordinary round-robin HTTP workers: each worker would
have a different previous-fact state and could emit incorrect deltas. Use
stateless mode for independently load-balanced requests. For independent batch
facts, process-based parallel evaluation is available through
`fluxrules.engine.runtime.evaluate_batch_parallel`; keep its
`streaming_mode=False` default. A streaming workload must instead shard by
stream identity and keep each shard ordered on one owner.

---

## Next Steps

- **The FluxRules Engine** — See [The FluxRules Engine](engine-comparison.md) for algorithm details
- **Choosing an Evaluation Mode** — See [Choosing an Evaluation Mode](choosing-an-engine.md) for selection logic
