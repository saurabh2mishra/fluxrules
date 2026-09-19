# Examples

FluxRules includes a complete runnable examples suite covering beginner to advanced usage.

## Verification Status

All scripts listed on this page were executed successfully on 2026-07-01.

- Total scripts: 29
- Passing scripts: 29
- Failures: 0

## Run Examples

Run a single example:

```bash
uv run python examples/00_getting_started.py
```

Run all examples:

```bash
for f in examples/0*.py examples/1*.py examples/2*.py; do
	echo "Running: $f"
	uv run python "$f"
done
```

## Learning Path

### Fundamentals

- `00_getting_started.py`: first engine and first rule evaluation.
- `01_conditions.py`: operator behavior and condition patterns.
- `02_complex_conditions.py`: nested AND/OR logic.

### Rule Organization and Validation

- `03_domains_and_tags.py`: rule grouping and filtering strategies.
- `04_validation.py`: validation workflows before execution.

### Persistence and Stateful Flows

- `05_persistence.py`: rule persistence patterns.
- `06_working_memory.py`: state retention across evaluations.

### Rules as Data

- `07_yaml_rules.py`: YAML-driven rule definitions.
- `08_decision_table.py`: CSV decision-table style authoring.

### Engine Architecture and Extensibility

- `09_custom_engines.py`: custom engine implementation.
- `10_pluggable_engines.py`: swapping engines with stable rule intent.

### Integration Paths

- `11_cli_usage.py`: command-line workflows.
- `12_api_usage.py`: HTTP API integration.
- `22_real_world_workflow.py`: end-to-end operational workflow.

### Advanced Modeling

- `13_complex_rules.py`: multi-stage decision logic.
- `14_error_handling.py`: defensive evaluation and failure handling.
- `16_fact_store.py`: fact storage and retrieval usage.
- `17_id_generation.py`: deterministic and strategy-based IDs.
- `18_unified_rule.py`: unified rule model workflows.
- `19_advanced_features.py`: combined advanced patterns.

### Streaming, Actions, and Pipelines

- `15_action_system.py`: action execution model.
- `20_streaming_mode.py`: continuous/stream-oriented evaluation.
- `21_action_registry.py`: action registration and dispatch.
- `23_streaming_vs_stateless.py`: stateful vs one-shot behavior.
- `24_cross_fact_joins.py`: multi-fact relationship matching.
- `25_nested_facts.py`: nested object traversal.
- `26_fact_loader.py`: heterogeneous fact ingestion.
- `27_factpipeline.py`: composable fact pipeline.
- `28_factpipeline_tier1.py`: tiered pipeline architecture.
- `29_custom_transforms.py`: custom transformation stages.

## Related Guides

- [Advanced Capabilities](advanced-capabilities.md)
- [Python API](python-api.md)
- [HTTP API](http-api.md)
