# Advanced Capabilities

FluxRules does more than match one condition against one fact. This page maps
each advanced capability to the guide that explains it and to a runnable
example that shows it working.

Run any example from the `examples/` folder, for example
`cd examples && python 20_streaming_mode.py`.

## Capability map

| Capability | What it enables | Guide | Examples |
|---|---|---|---|
| Every way to evaluate | One call, an engine, models, batches across processes, streaming, a cache and sessions, side by side | [Ways to Evaluate a Fact](evaluating-facts.md) | [32_ways_to_evaluate.py][ex32] |
| Evaluation modes | Stateless by default, or streaming for a long-lived stream of updates | [Choosing an Evaluation Mode](choosing-an-engine.md) | [20_streaming_mode.py][ex20], [23_streaming_vs_stateless.py][ex23] |
| Working memory | Hold the facts of a session and retract them later | [Working Memory](working-memory.md) | [06_working_memory.py][ex06] |
| Typed facts | Evaluate Pydantic models and dataclasses, and check rule fields against a model | [Typed Facts](typed-facts.md) | [31_typed_facts.py][ex31] |
| Nested facts | Match nested input by flattening it first | [Nested Facts](nested-facts.md) | [25_nested_facts.py][ex25] |
| Cross-fact joins | Rules that relate two facts, such as a payment and its customer | [Cross-Fact Rules](cross-fact-rules.md) | [24_cross_fact_joins.py][ex24] |
| Fact pipelines | Clean, validate and enrich raw input before evaluation | [Fact Pipeline](fact-pipeline.md) | [26_fact_loader.py][ex26], [27_factpipeline.py][ex27], [28_factpipeline_tier1.py][ex28] |
| Custom transforms | Add your own cleaning and enrichment steps to a pipeline | [Custom Transforms](custom-transforms.md) | [29_custom_transforms.py][ex29] |
| Complex decision logic | Nested AND, OR and NOT across many checks | [Complex Conditions](complex-conditions.md) | [13_complex_rules.py][ex13] |
| Rules as data | Keep complete rules, conditions included, in a YAML file | [YAML Rules](yaml-rules.md) | [07_yaml_rules.py][ex07] |
| Validation | Catch malformed rules before they run | [Validation Framework](validation-framework.md) | [04_validation.py][ex04] |
| Rule analysis | Find rules that overlap, conflict or can never fire | [Rule Analysis](rule-analysis.md) | [30_conflict_detection.py][ex30] |
| Actions | Run code when a rule fires, and describe your actions | [Actions](custom-actions.md) | [15_action_system.py][ex15], [21_action_registry.py][ex21] |
| Custom engines | Change how matched rules are chosen, and pick an engine by name | [Custom Engines](custom-engines.md) | [09_custom_engines.py][ex09], [10_pluggable_engines.py][ex10] |
| CLI and HTTP API | Evaluate rules from scripts and from other services | [CLI](cli.md), [HTTP API](api.md) | [11_cli_usage.py][ex11] (needs `fluxrules[cli]`), [12_api_usage.py][ex12] (needs `fluxrules[api]`) |
| A full workflow | Validate, normalize, evaluate, act and explain, end to end | [From Fact to Action](fact-to-action.md) | [22_real_world_workflow.py][ex22] |

## Where to begin

If you are new to these features, read them in this order:

1. [Ways to Evaluate a Fact](evaluating-facts.md), to see every entry point
   side by side.
2. [Typed Facts](typed-facts.md) and [Fact Pipeline](fact-pipeline.md), to
   get input into the shape your rules expect.
3. [Extension Points](extension-points.md), to see what you can replace with
   your own code.

## Verification note

Every example on this page was run successfully on 2026-10-21 with the `dev`
dependency group installed.

[ex04]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/04_validation.py
[ex06]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/06_working_memory.py
[ex07]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/07_yaml_rules.py
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
[ex30]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/30_conflict_detection.py
[ex31]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/31_typed_facts.py
[ex32]: https://github.com/saurabh2mishra/fluxrules/blob/main/examples/32_ways_to_evaluate.py
