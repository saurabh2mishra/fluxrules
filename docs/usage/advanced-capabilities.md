# Advanced Capabilities

FluxRules supports much more than basic condition matching. This page maps advanced capabilities to runnable examples so each claim is backed by executable code.

## Capability Map

| Capability | What it enables | Primary examples |
|---|---|---|
| Multiple engine implementations | Choose behavior and performance profile by workload | `09_custom_engines.py`, `10_pluggable_engines.py`, `23_streaming_vs_stateless.py` |
| Stateful evaluation | Keep and reuse context across evaluations | `06_working_memory.py`, `20_streaming_mode.py` |
| Rules as data | Author and load rules from YAML | `07_yaml_rules.py` |
| Extensible actions | Register and execute custom actions | `15_action_system.py`, `21_action_registry.py` |
| Complex decision modeling | Express nested logic and multi-fact scenarios | `13_complex_rules.py`, `24_cross_fact_joins.py`, `25_nested_facts.py` |
| Fact normalization pipeline | Transform heterogeneous inputs before evaluation | `26_fact_loader.py`, `27_factpipeline.py`, `28_factpipeline_tier1.py`, `29_custom_transforms.py` |
| API and CLI integration | Embed rule evaluation in service and automation paths | `11_cli_usage.py`, `12_api_usage.py`, `22_real_world_workflow.py` |

## Advanced Evaluation Patterns

### Engine mode as a runtime concern

Use different evaluation modes for different workloads. You can keep rule definitions stable while swapping the execution strategy.

- Use `PhreakEngine` (stateless, default) for high-throughput request-response evaluation.
- Use `PhreakEngine(streaming_mode=True)` when you need incremental deltas across a session.

See `10_pluggable_engines.py` for switching evaluation modes while keeping the same rule intent.

### Stateful versus stateless execution

FluxRules supports both one-shot evaluation and stateful flows.

- Stateless: evaluate facts independently.
- Stateful: keep working memory/session context and evaluate incrementally.

See `23_streaming_vs_stateless.py` for a side-by-side comparison and `06_working_memory.py` for state retention patterns.

### Cross-fact and nested data reasoning

You can express nested condition logic and evaluate relationships between multiple facts. Engines evaluate flat key-value facts, so nested input must be **pre-flattened** into dotted (or otherwise flattened) keys before evaluation; engines do not traverse nested dictionaries at match time.

- Cross-fact joins: `24_cross_fact_joins.py`
- Pre-flattened nested facts: `25_nested_facts.py`

These patterns are useful in fraud, eligibility, and compliance workflows where single-row checks are not enough.

## Extensibility Surface

### Custom engines

You can implement custom engine behavior and still integrate with the surrounding FluxRules flow. See `09_custom_engines.py`.

### Action system and registry

You can define reusable action handlers and register them for rule-triggered behavior. See:

- `15_action_system.py`
- `21_action_registry.py`

### Fact pipeline and transforms

For heterogeneous input data, normalize before evaluation using loader and pipeline stages:

- `26_fact_loader.py`
- `27_factpipeline.py`
- `28_factpipeline_tier1.py`
- `29_custom_transforms.py`

## Deep-Dive Pages

These pages cover advanced areas in more detail:

- [Action Registry](../action-registry.md)
- [Fact Pipeline](../fact-pipeline.md)
- [Cross-Fact Rules](../cross-fact-rules.md)
- [Nested Facts](../nested-facts.md)
- [Validation Framework](../validation-framework.md)
- [Working Memory](../working-memory.md)
- [Custom Engines](../custom-engines.md)
- [Custom Transforms](../custom-transforms.md)

## Verification Note

All examples listed in this page were executed successfully in repository verification on 2026-07-01.
