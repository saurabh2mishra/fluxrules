# Examples & Learning Path

Welcome to the FluxRules learning path! This guide walks you through progressively more sophisticated examples that teach you how to build rules in FluxRules. 

**All examples use a shared `cross_border_payment_risk_triage` dataset** located in `examples/shared_use_case.py`. This means you can focus on learning each feature without switching between different problem domains. Each example is a standalone Python script in the `examples/` directory.

**Estimated time:** 30 minutes to run all examples end-to-end.

## Learning Path Overview

All examples share a common **payment-risk triage** use case with cross-border fraud detection rules. This lets you focus on learning each feature without context switching between different problem domains.

| Group | Examples | Focus |
|-------|----------|-------|
| **Basics** | 00-04 | Getting started, conditions, complex conditions, domains/tags, validation |
| **Integration** | 05-11 | Persistence, working memory, YAML, engines, CLI, REST API |
| **Advanced** | 13-22 | Complex rules, error handling, actions, fact store, ID generation, unified rules, streaming, workflows |
| **Pipelines** | 23-30 | Stateless evaluation, cross-fact joins, nested facts, fact loading, pipelines, transforms, conflict detection |

---

## Basics (30 minutes)

### Example 00: Getting Started
**File:** `examples/00_getting_started.py`

Your first rule engine! This example shows:
- Creating a rule engine
- Defining a simple rule with one condition
- Running facts through the engine
- Inspecting results

**Key Concepts:** Engine, Rule, Condition, Fact

**Run it:**
```bash
python examples/00_getting_started.py
```

### Example 01: Conditions
**File:** `examples/01_conditions.py`

Deep dive into condition types. Learn:
- Different condition operators (equality, comparison, pattern matching)
- Building conditions with the validation framework
- Debugging condition evaluation

**Key Concepts:** Validation Framework, Conditions, Operators

**Run it:**
```bash
python examples/01_conditions.py
```

### Example 02: Complex Conditions
**File:** `examples/02_complex_conditions.py`

Combine conditions with logic. Learn:
- AND/OR logic between conditions
- Condition groups and precedence
- Nested conditions

**Key Concepts:** Condition Logic, Groups, Precedence

**Run it:**
```bash
python examples/02_complex_conditions.py
```

---

## Organization (45 minutes)

### Example 03: Domains and Tags
**File:** `examples/03_domains_and_tags.py`

Organize your rules at scale. Learn:
- What are domains and why they matter
- Tagging rules for organization and filtering
- Querying rules by domain and tags
- Domain-specific validation

**Key Concepts:** Domains, Tags, Rule Organization, Filtering

**Run it:**
```bash
python examples/03_domains_and_tags.py
```

### Example 04: Validation
**File:** `examples/04_validation.py`

Ensure data quality and correctness. Learn:
- Rule validation
- Fact validation against schemas
- Error handling and messages
- Pre-execution validation

**Key Concepts:** Validation, Error Handling, Data Quality

**Run it:**
```bash
python examples/04_validation.py
```

---

## Persistence (45 minutes)

### Example 05: Persistence
**File:** `examples/05_persistence.py`

Save and load rules from databases. Learn:
- Persisting rules to SQLite/PostgreSQL
- Loading rules from disk
- Database schema and migrations
- Versioning rules

**Key Concepts:** Persistence, Databases, Versioning

**Run it:**
```bash
python examples/05_persistence.py
```

### Example 06: Working Memory
**File:** `examples/06_working_memory.py`

Maintain state between rule executions. Learn:
- What is working memory?
- Adding facts to working memory
- Querying working memory
- Using working memory for complex workflows

**Key Concepts:** Working Memory, State, Sessions

**Run it:**
```bash
python examples/06_working_memory.py
```

---

## Rules as Data (60 minutes)

### Example 07: YAML Rules
**File:** `examples/07_yaml_rules.py`

Define rules in YAML format. Learn:
- YAML rule syntax
- Loading rules from files
- Rule definitions without code
- Domain-specific configurations

**Key Concepts:** YAML, Declarative Rules, File-based Configuration

**Run it:**
```bash
python examples/07_yaml_rules.py
```

---

## Advanced Features (2+ hours)

### Example 09: Custom Engines
**File:** `examples/09_custom_engines.py`

Build your own rule engine. Learn:
- Engine interface and lifecycle
- Implementing a custom engine
- Optimization opportunities
- When to use custom engines

**Key Concepts:** Custom Engines, Architecture, Extensibility

**Run it:**
```bash
python examples/09_custom_engines.py
```

### Example 10: Pluggable Engines
**File:** `examples/10_pluggable_engines.py`

Switch engines at runtime. Learn:
- Engine registration and discovery
- Using the engine factory
- Switching between engines
- Benchmarking different engines

**Key Concepts:** Pluggable Architecture, Factory Pattern, Engine Selection

**Run it:**
```bash
python examples/10_pluggable_engines.py
```

### Example 11: CLI Usage
**File:** `examples/11_cli_usage.py`

Use FluxRules from the command line. Learn:
- CLI interface
- Loading rules and facts
- Producing reports
- Scripting with FluxRules

**Key Concepts:** CLI, Scripting, Automation

**Run it:**
```bash
python examples/11_cli_usage.py
```

### Example 12: REST API Usage
**File:** `examples/12_api_usage.py`

Call FluxRules over HTTP. Learn:
- Starting a REST API server
- Calling rules via HTTP
- Integration patterns
- Error handling

**Key Concepts:** REST API, HTTP, Integration

**Run it:**
```bash
python examples/12_api_usage.py
```

### Example 13: Complex Rules
**File:** `examples/13_complex_rules.py`

Build real-world rule systems. Learn:
- Chaining rules together
- Multi-stage rule evaluation
- Stateful rule workflows
- Complex action systems

**Key Concepts:** Rule Chains, Workflows, Advanced Actions

**Run it:**
```bash
python examples/13_complex_rules.py
```

### Example 14: Rule Builder
**File:** `examples/14_rule_builder.py`

Use the fluent rule builder API. Learn:
- The Rule Builder pattern
- Fluent API for rule construction
- DSL-like rule definitions
- Type safety and IDE support

**Key Concepts:** Builder Pattern, Fluent API, DSLs

**Run it:**
```bash
python examples/14_rule_builder.py
```

### Example 15: Action System
**File:** `examples/15_action_system.py`

Master the action system. Learn:
- Built-in actions (set, increment, transform)
- Custom action implementations
- Action chains and pipelines
- Action context and execution

**Key Concepts:** Actions, Custom Actions, Action Pipelines

**Run it:**
```bash
python examples/15_action_system.py
```

### Example 16: Fact Store
**File:** `examples/16_fact_store.py`

Manage facts at scale. Learn:
- Fact storage and retrieval
- Indexing for performance
- Querying facts efficiently
- Fact lifecycle management

**Key Concepts:** Fact Store, Indexing, Performance

**Run it:**
```bash
python examples/16_fact_store.py
```

### Example 17: ID Generation
**File:** `examples/17_id_generation.py`

Generate and manage rule IDs. Learn:
- ID generation strategies
- UUIDs, sequential IDs, custom IDs
- ID tracking and versioning
- ID resolution in rule chains

**Key Concepts:** ID Generation, Versioning, Tracking

**Run it:**
```bash
python examples/17_id_generation.py
```

### Example 18: Unified Rule Engine
**File:** `examples/18_unified_rule.py`

The flagship example showcasing the unified engine. Learn:
- All components working together
- Multi-domain rule systems
- Full lifecycle workflows
- Production-ready patterns

**Key Concepts:** Unified Engine, Integration, Best Practices

**Run it:**
```bash
python examples/18_unified_rule.py
```

### Example 19: Advanced Features
**File:** `examples/19_advanced_features.py`

Deep dives into advanced capabilities. Learn:
- Performance analysis and latency measurement
- Statistics and metrics from evaluations
- Working with complex rule sets at scale

**Key Concepts:** Performance, Latency, Metrics

**Run it:**
```bash
python examples/19_advanced_features.py
```

---

## Data Processing Pipelines (2+ hours)

### Example 20: Streaming Mode
**File:** `examples/20_streaming_mode.py`

Process facts as a stream. Learn:
- Streaming fact processing
- Latency measurement per fact
- Incremental evaluation
- Pipeline throughput

**Key Concepts:** Streaming, Incremental Processing

**Run it:**
```bash
python examples/20_streaming_mode.py
```

### Example 21: Action Registry
**File:** `examples/21_action_registry.py`

Manage and track actions. Learn:
- Extracting unique actions from rules
- Action execution counts
- Action registry patterns
- Tracking action usage

**Key Concepts:** Action Registry, Tracking, Metrics

**Run it:**
```bash
python examples/21_action_registry.py
```

### Example 22: Real-World Workflow
**File:** `examples/22_real_world_workflow.py`

End-to-end production workflow. Learn:
- Real-world transaction triage
- Multi-step decision logic
- Audit trail integration
- Production-ready patterns

**Key Concepts:** Workflows, Production Patterns, Audit Trails

**Run it:**
```bash
python examples/22_real_world_workflow.py
```

---

## Advanced Data Processing (2+ hours)

### Example 23: Streaming vs Stateless
**File:** `examples/23_streaming_vs_stateless.py`

Compare evaluation modes. Learn:
- Stateless evaluation (default)
- Streaming evaluation characteristics
- Performance differences
- When to use each mode

**Key Concepts:** Evaluation Modes, Stateless Processing

**Run it:**
```bash
python examples/23_streaming_vs_stateless.py
```

### Example 24: Cross-Fact Joins
**File:** `examples/24_cross_fact_joins.py`

Relate multiple facts. Learn:
- Processing multiple facts together
- Cross-fact pattern detection
- Relational evaluation
- Fact correlation

**Key Concepts:** Cross-Fact Joins, Relational Logic

**Run it:**
```bash
python examples/24_cross_fact_joins.py
```

### Example 25: Nested Facts
**File:** `examples/25_nested_facts.py`

Work with hierarchical data. Learn:
- Nested fact structures
- Accessing nested fields
- Hierarchical condition evaluation
- Complex data models

**Key Concepts:** Nested Structures, Hierarchical Data

**Run it:**
```bash
python examples/25_nested_facts.py
```

### Example 26: Fact Loader
**File:** `examples/26_fact_loader.py`

Load facts at scale. Learn:
- Batch fact loading
- Fact preprocessing
- Large-scale processing
- Throughput optimization

**Key Concepts:** Fact Loading, Batch Processing

**Run it:**
```bash
python examples/26_fact_loader.py
```

### Example 27: FactPipeline
**File:** `examples/27_factpipeline.py`

Pipeline-based fact processing. Learn:
- Multi-stage fact pipelines
- Loading, enrichment, evaluation workflow
- Result output and formatting
- End-to-end data flow

**Key Concepts:** Fact Pipelines, ETL, Data Flow

**Run it:**
```bash
python examples/27_factpipeline.py
```

### Example 28: FactPipeline (Tier 1)
**File:** `examples/28_factpipeline_tier1.py`

High-priority rule filtering. Learn:
- Filtering rules by tags
- Tier-based rule organization
- Priority-based evaluation
- Optimized rule selection

**Key Concepts:** Rule Tiers, Filtering, Priority

**Run it:**
```bash
python examples/28_factpipeline_tier1.py
```

### Example 29: Custom Transforms
**File:** `examples/29_custom_transforms.py`

Transform facts before evaluation. Learn:
- Custom fact enrichment
- Computed field addition
- Data transformation pipelines
- Pre-evaluation preprocessing

**Key Concepts:** Transforms, Data Enrichment, Preprocessing

**Run it:**
```bash
python examples/29_custom_transforms.py
```

### Example 30: Conflict Detection
**File:** `examples/30_conflict_detection.py`

Analyze rule coverage and conflicts. Learn:
- Rule coverage analysis
- Rule firing statistics
- Conflict detection
- Rule health assessment

**Key Concepts:** Conflict Detection, Rule Analysis, Coverage

**Run it:**
```bash
python examples/30_conflict_detection.py
```

---

## Running All Examples

To run all examples in sequence:

```bash
cd examples
for file in *.py; do
    echo "Running $file..."
    python "$file"
done
```

## Quick Reference

### Running Examples

**Run a single example:**
```bash
cd examples
python 00_getting_started.py
python 13_complex_rules.py
```

**Run all examples:**
```bash
cd examples
for file in [0-3][0-9]_*.py; do
    echo "Running $file..."
    python "$file"
done
```

### Shared Dataset (`examples/shared_use_case.py`)

All examples use the same payment-risk dataset. Run examples from the `examples/` directory:

```python
# python skip
# Each example imports from the local shared_use_case module
# Run from: cd examples && python 00_getting_started.py

# Inside examples/00_getting_started.py:
import sys
sys.path.insert(0, '.')  # Add current directory to path

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, build_shared_rules, complex_risk_condition

# Shared facts (3 test transactions)
for fact in SHARED_FACTS:
    print(fact["fact_id"])  # txn-001, txn-002, txn-003

# Shared rules (3 risk-triage rules)
rules = build_shared_rules()

# Shared DSL (8-condition nested payment-risk rule)
dsl = complex_risk_condition()
```

---

## Next Steps

After completing the learning path:

1. **Read the [Unified Validation Framework](validation-framework.md)** to understand the core validation system
2. **Review [The FluxRules Engine](engine-comparison.md)** to pick the right evaluation mode for your use case
3. **Explore [Custom Engines](custom-engines.md)** to extend FluxRules
4. **Check [Troubleshooting](troubleshooting.md)** for common issues

---

## Tips for Learning

- **Run each example:** Don't just read the code; execute it and modify it
- **Experiment:** Change conditions, add rules, see what happens
- **Debug:** Use print statements and the engine's debug mode
- **Build:** Create your own rules based on the patterns you see
- **Integrate:** Try using FluxRules in your own projects

Happy rule engineering! 
