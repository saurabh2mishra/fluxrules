# Advanced Capabilities

FluxRules does more than match one condition against one fact. This page maps
each advanced capability to a runnable example, so every claim is backed by code
you can read and run.

Run any example from the `examples/` folder, for example
`cd examples && python 20_streaming_mode.py`.

## Capability Map

| Capability | What it enables | Examples |
|---|---|---|
| Custom engines and the engine registry | Change how matched rules are chosen, and pick an engine by name | [09_custom_engines.py][ex09], [10_pluggable_engines.py][ex10] |
| Evaluation modes | Stateless by default, or streaming for a long-lived stream of updates | [20_streaming_mode.py][ex20], [23_streaming_vs_stateless.py][ex23] |
| Working memory | Hold the facts of a session and retract them later | [06_working_memory.py][ex06] |
| Rules as data | Keep complete rules, conditions included, in a YAML file | [07_yaml_rules.py][ex07] |
| Actions | Run code when a rule fires, and describe your actions | [15_action_system.py][ex15], [21_action_registry.py][ex21] |
| Complex decision logic | Nested AND, OR and NOT across many checks | [13_complex_rules.py][ex13] |
| Cross-fact joins | Rules that relate two facts, such as a payment and its customer | [24_cross_fact_joins.py][ex24] |
| Nested facts | Match nested input by flattening it first | [25_nested_facts.py][ex25] |
| Fact pipelines | Clean, validate and enrich raw input before evaluation | [26_fact_loader.py][ex26], [27_factpipeline.py][ex27], [28_factpipeline_tier1.py][ex28], [29_custom_transforms.py][ex29] |
| CLI and HTTP API | Evaluate rules from scripts and from other services | [11_cli_usage.py][ex11] (needs `fluxrules[cli]`), [12_api_usage.py][ex12] (needs `fluxrules[api]`) |
| A full workflow | Validate, normalize, evaluate, act and explain, end to end | [22_real_world_workflow.py][ex22] |

## Advanced Evaluation Patterns

### Choosing an evaluation mode

The same rules run in two modes. You choose the mode when you create the engine.

- **Stateless** (`PhreakEngine()`, the default) answers every call in full. Any
  instance can serve any request, so it suits request-response services behind a
  load balancer.
- **Streaming** (`PhreakEngine(streaming_mode=True)`) remembers the previous call.
  It skips a fact identical to the last one and re-evaluates a changed one. One
  stream must always reach the same instance.

[20_streaming_mode.py][ex20] sends a stream of updates to a streaming engine, and
[23_streaming_vs_stateless.py][ex23] sends the same stream to both modes side by
side. [10_pluggable_engines.py][ex10] creates both by name through the engine
registry.

### Working memory

`PhreakEngine.assert_fact` stores a fact and returns an id, and `retract_fact`
removes it. Stored facts do not change what `evaluate()` returns, which always
works on the fact you pass in. [06_working_memory.py][ex06] asserts the shared
transactions, evaluates them and retracts one.

### Cross-fact and nested data

`PhreakEngine` evaluates one flat fact at a time. Two patterns cover data that
does not fit that shape:

- **Facts that must be related to each other**: use `CrossFactEngine`. It keeps
  typed facts in memory and fires when a tuple of facts matches, for example a
  payment over 2000 joined to a customer whose account is under 14 days old. An
  update or retract removes the matches that depended on the fact. See
  [24_cross_fact_joins.py][ex24].
- **Nested input**: the engine does not walk into nested dictionaries, so flatten
  first with the `Flatten` transform. `{"payment": {"amount": 4200}}` becomes
  `{"payment.amount": 4200}`, and rules use the dotted name. See
  [25_nested_facts.py][ex25].

### Rules as data

A rule can live entirely in a YAML file: metadata and conditions, written in the
same dict format that F expressions produce. [07_yaml_rules.py][ex07] loads
[payment_risk_rules.yaml][rules07] with `load_rules_from_yaml`, builds each rule
with `Rule.model_validate_yaml`, and checks that the YAML triage rule decides
every shared fact the same way as the F-built version.

## Extensibility Surface

### Custom engines

Subclass `BaseEngine` and override `_evaluate_rules` to decide which candidate
rules fire. [09_custom_engines.py][ex09] builds a first-match engine that fires
only the highest-priority matching rule, registers it with `register_engine`, and
compares it with `PhreakEngine` on the same facts.

### Actions

A rule's action is a name. `evaluate()` returns the names that fired and your
application runs them.

- [15_action_system.py][ex15] registers a handler per action with `@action` and
  dispatches the fired actions with `action_registry.execute`.
- [21_action_registry.py][ex21] shows what the registry records: descriptions,
  categories, parameters, and async handlers run with `execute_async`.

### Fact pipelines and transforms

Normalize raw input before evaluation:

- [26_fact_loader.py][ex26] loads a batch with `FactLoader` and collects bad rows
  in a dead-letter list instead of stopping.
- [27_factpipeline.py][ex27] covers the framework: built-in transforms,
  composition with `>>` and `|`, metrics with `MetricsHook`, and versioning with
  `diff_pipelines`.
- [28_factpipeline_tier1.py][ex28] splits a pipeline into clean, validate and
  enrich tiers.
- [29_custom_transforms.py][ex29] writes custom stages by subclassing `Transform`.

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

Every example on this page was run successfully on 2026-10-21 with the `dev`
extras installed.

[ex06]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/06_working_memory.py
[ex07]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/07_yaml_rules.py
[rules07]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/payment_risk_rules.yaml
[ex09]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/09_custom_engines.py
[ex10]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/10_pluggable_engines.py
[ex11]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/11_cli_usage.py
[ex12]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/12_api_usage.py
[ex13]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/13_complex_rules.py
[ex15]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/15_action_system.py
[ex20]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/20_streaming_mode.py
[ex21]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/21_action_registry.py
[ex22]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/22_real_world_workflow.py
[ex23]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/23_streaming_vs_stateless.py
[ex24]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/24_cross_fact_joins.py
[ex25]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/25_nested_facts.py
[ex26]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/26_fact_loader.py
[ex27]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/27_factpipeline.py
[ex28]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/28_factpipeline_tier1.py
[ex29]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/29_custom_transforms.py
