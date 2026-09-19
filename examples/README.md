# FluxRules Examples Directory

Welcome! This directory contains **comprehensive, practical examples** demonstrating FluxRules capabilities from basic to advanced.

**All examples are runnable, tested, and demonstrate real-world patterns.**

---

## ⭐ Recommended: Start with Pydantic Rule (Simplified Approach)

**NEW!** FluxRules now recommends the simplified **Pydantic Rule** approach for creating rules:

```python
from fluxrules import Rule  # same class as fluxrules.domain.Rule
from fluxrules.engine.phreak import PhreakEngine

# Create rules with auto-generated IDs
rule = Rule(
    name="High Value Transaction",
    condition_dsl={
        "type": "condition",
        "field": "amount",
        "op": ">",
        "value": 1000,
    },
    action="flag_for_review",
    priority=10,
    persist=False,  # keep it in memory
)

# Use in your engine
engine = PhreakEngine()
engine.load_rules([rule])
result = engine.evaluate({"amount": 1500})
print(result.fired_rules)  # Auto-generated rule ID
```

✅ **Why Pydantic Rule?**
- Simpler syntax (no method chaining)
- Auto-generated IDs (no manual management)
- Better IDE support
- Consistent across all creation paths (CSV, YAML, API, etc.)
- Less boilerplate

👉 **See [18_unified_rule.py](18_unified_rule.py) for comprehensive Pydantic Rule examples**
👉 **Read the [Pydantic Rule Guide](../docs/pydantic-rule-guide.md) for the full reference**
👉 **Unsure which `Rule` to use? [Rule Types](../docs/rule-types.md) answers it in 30 seconds**

---

## 🎯 Quick Start

```bash
cd /path/to/fluxrules

# Run the simplified rule example
python examples/18_unified_rule.py

# Or start with basics
python examples/00_getting_started.py
```

### 📚 Learning Path

**New to FluxRules?** Start with the [Learning Path Guide](../docs/examples.md) for a structured progression through all concepts and examples.

---

## 📚 Learning Path

**Recommended:** Start with the Core Concepts group, then jump to example **18** (Pydantic Rule) to learn the simplified approach.

Complete the examples **in order** within each group to build a solid foundation.

### Documentation References

Each group has corresponding comprehensive documentation guides. Use these alongside the examples for deeper understanding:

**Core Concepts**
- 📖 [Simple Conditions Guide](../docs/conditions.md) - Master all 10 operators
- 📖 [Complex Conditions Guide](../docs/complex-conditions.md) - AND/OR logic and nesting
- 📖 [Domain & Tags Organization](../docs/domains-and-tags.md) - Organize at scale

**Data Management**
- 📖 [Working Memory Guide](../docs/working-memory.md) - Stateful rule evaluation
- 📖 [Sessions & State Management](../docs/sessions.md) - Long-running workflows
- 📖 [YAML & CSV Rules](../docs/yaml-csv-rules.md) - Rules as configuration

**Engine & Architecture**
- 📖 [Engine Comparison Guide](../docs/engine-comparison.md) - Choose the right engine

**Integration & DevOps**
- 📖 [REST API Server Guide](../docs/rest-api.md) - Deploy as a microservice

**Advanced Techniques**
- 📖 [Rule Builder API](../docs/rule-builder.md) - Fluent programming interface
- 📖 [Troubleshooting Guide](../docs/troubleshooting.md) - Common issues and solutions

---

### Core Concepts (Start Here!) - ~50 minutes

Master the basics before moving on.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **18** | `18_unified_rule.py` | ⭐ **Pydantic Rule** - Simplified rule creation (RECOMMENDED) | 10 min |
| **00** | `00_getting_started.py` | 3-step process: Create → Define → Evaluate | 5 min |
| **01** | `01_conditions.py` | Master all operators (==, !=, in, regex, etc.) | 10 min |
| **02** | `02_complex_conditions.py` | AND/OR logic & nested conditions | 10 min |
| **03** | `03_domains_and_tags.py` | Organize rules by domain & tags | 10 min |
| **04** | `04_validation.py` | Ensure rule quality before production | 15 min |

### Data Management - ~45 minutes

Learn how to persist, manage state, and load rules from files.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **05** | `05_persistence.py` | Save & load rules from database | 10 min |
| **06** | `06_working_memory.py` | Stateful evaluation with assert/retract | 15 min |
| **07** | `07_yaml_rules.py` | Load rules from YAML (DevOps-friendly) | 10 min |
| **08** | `08_decision_table.py` | CSV-based rules for business analysts | 10 min |

### Engine & Architecture - ~25 minutes

Understand different engines and when to use them.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **09** | `09_custom_engines.py` | Build custom engines from the BaseEngine base class | 15 min |
| **10** | `10_pluggable_engines.py` | Use the engine registry; stateless vs streaming PHREAK modes | 10 min |

### Integration & DevOps - ~25 minutes

Integrate FluxRules into your application and deployment pipeline.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **11** | `11_cli_usage.py` | Command-line interface for automation | 10 min |
| **12** | `12_api_usage.py` | REST API server (FastAPI) | 15 min |

### Advanced Techniques - ~35 minutes

Master advanced patterns and enterprise features.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **13** | `13_complex_rules.py` | All 10 operators in real-world scenarios | 15 min |
| **14** | `14_rule_builder.py` | Type-safe rule builders | 10 min |
| **15** | `15_action_system.py` | Execute actions after rule matching | 10 min |
| **16** | `16_fact_store.py` | Fact lifecycle management & auditing | 10 min |
| **17** | `17_id_generation.py` | Auto ID generation for rules | 10 min |
| **18** | `18_unified_rule.py` | Unified rule creation interface | 10 min |
| **19** | `19_advanced_features.py` | Advanced patterns and features | 10 min |
| **20** | `20_streaming_mode.py` | Streaming mode for continuous evaluation | 10 min |
| **21** | `21_action_registry.py` | Decorator-based action registry system | 10 min |
| **23** | `23_streaming_vs_stateless.py` | Streaming delta vs stateless contracts (sticky routing) | 10 min |

**Total to master all examples: ~200 minutes (~3.5 hours)**

### Data Ingestion & Pipelines - ~45 minutes

Get heterogeneous facts (JSON, CSV, streams) into the engine cleanly.

| # | Example | Focus | Time |
|---|---------|-------|------|
| **24** | `24_cross_fact_joins.py` | Cross-fact joins across working memory | 10 min |
| **25** | `25_nested_facts.py` | Flatten nested facts to dot notation | 10 min |
| **26** | `26_fact_loader.py` | DataLoader-style fact pipeline (prototype) | 15 min |
| **27** | `27_factpipeline.py` | ⭐ **FactPipeline framework** (type-safe transforms, composition, observability, versioning) | 15 min |
| **28** | `28_factpipeline_tier1.py` | Tiered pipeline architecture | 15 min |
| **29** | `29_custom_transforms.py` | Writing your own transform stages | 15 min |
| **30** | `30_conflict_detection.py` | ⭐ **Rule health**: conflicts, coverage gaps, shadowed rules | 15 min |

---

## 🚀 Running Examples

### Run a Single Example
```bash
python examples/00_getting_started.py
python examples/05_persistence.py
python examples/12_api_usage.py
```

### Run All Examples Sequentially
```bash
for i in {00..21}; do
  f="examples/$(printf '%02d' $i)_*.py"
  if [ -f "$f" ]; then
    echo "=== Running $(basename $f) ==="
    python "$f" || echo "Failed: $(basename $f)"
    echo ""
  fi
done
```

### Run with Output to File
```bash
python examples/00_getting_started.py > output.txt 2>&1
```

---

## 🎓 Learning Recommendations by Role

### For Beginners (First Time Users)
1. **Start:** `00_getting_started.py` (5 min)
2. **Learn Operators:** `01_conditions.py` (10 min)
3. **Complex Logic:** `02_complex_conditions.py` (10 min)
4. **Organization:** `03_domains_and_tags.py` (10 min)
5. **Quality:** `04_validation.py` (15 min)

**Next:** Continue with the data management examples.

### For Business Analysts
Focus on rule authoring and validation:
1. `03_domains_and_tags.py` - Understand rule organization
2. `08_decision_table.py` - Author rules in CSV format
3. `04_validation.py` - Ensure quality before deployment
4. `01_conditions.py` - Reference for all operators
5. `07_yaml_rules.py` - Configuration management

### For Software Architects
Focus on design, customization, and integration:
1. `00_getting_started.py` - Understand the core paradigm
2. `09_custom_engines.py` - Design custom engines
3. `10_pluggable_engines.py` - Choose the right engine for your use case
4. `07_yaml_rules.py` - Configuration management for production
5. `12_api_usage.py` - REST API deployment patterns
6. `05_persistence.py` - Data durability and audit trails
7. `21_action_registry.py` - Decorator-based action system

### For DevOps & Platform Engineers
Focus on deployment, configuration, and operations:
1. `07_yaml_rules.py` - ConfigMap/secrets integration
2. `08_decision_table.py` - Business rules as configuration
3. `11_cli_usage.py` - CI/CD automation
4. `12_api_usage.py` - Microservices deployment
5. `16_fact_store.py` - Monitoring and observability

### For Performance Engineers
Focus on throughput, latency, and scalability:
1. `10_pluggable_engines.py` - Engine comparison and selection
2. `13_complex_rules.py` - Real-world complexity assessment
3. `06_working_memory.py` - Memory management patterns
4. Use `docs/benchmarks.md` for detailed performance data

---

## 📋 Topics by Use Case

### Fraud Detection
Examples demonstrating fraud detection patterns:
- `00_getting_started.py` - Basic fraud rules
- `02_complex_conditions.py` - Complex fraud detection logic
- `03_domains_and_tags.py` - Organizing fraud detection rules
- `13_complex_rules.py` - Enterprise-grade fraud system

### Compliance & Risk Management
Examples for regulatory compliance and risk assessment:
- `04_validation.py` - Rule quality assurance
- `07_yaml_rules.py` - Regulatory configurations
- `05_persistence.py` - Audit trails and compliance tracking
- `16_fact_store.py` - Change tracking and fact history

### Loan & Credit Applications
Examples for lending and credit scoring scenarios:
- `01_conditions.py` - Operator examples and references
- `03_domains_and_tags.py` - Multi-domain credit scoring
- `09_custom_engines.py` - Custom credit scoring engines
- `13_complex_rules.py` - Complex credit assessment rules

### DevOps & Cloud Native
Examples for container and Kubernetes deployments:
- `07_yaml_rules.py` - ConfigMap integration
- `08_decision_table.py` - Business rules as CSV/ConfigMaps
- `11_cli_usage.py` - CI/CD pipeline automation
- `12_api_usage.py` - Microservices and REST API deployment

### Event Processing & Streaming
Examples for real-time event processing:
- `06_working_memory.py` - Stateful event correlation
- `16_fact_store.py` - Event sourcing patterns
- `12_api_usage.py` - Streaming API integration

---

## ✅ Pre-Production Checklist

Before deploying FluxRules to production:

- [ ] **Understand Basics** - Complete the core concepts examples (00-04)
- [ ] **Validate Rules** - Run `04_validation.py` on all rules
- [ ] **Organize Rules** - Structure rules using `03_domains_and_tags.py` patterns
- [ ] **Data Durability** - Set up persistence using `05_persistence.py`
- [ ] **State Management** - Test working memory patterns if needed (`06_working_memory.py`)
- [ ] **Configuration** - Set up deployment configuration (`07_yaml_rules.py` or `12_api_usage.py`)
- [ ] **Monitoring** - Set up fact store and observability (`16_fact_store.py`)
- [ ] **Performance** - Load test and choose engine (`10_pluggable_engines.py`)
- [ ] **Integration** - Test API integration patterns (`12_api_usage.py`)
- [ ] **Documentation** - Document all rules and their domains
- [ ] **Review** - Get domain expert and security review

---

## 🔍 Troubleshooting

### Example Won't Run

**Problem:** `ModuleNotFoundError` or import errors

**Solution:**
```bash
# Install FluxRules in development mode
pip install -e .

# Or run from project root
cd /path/to/fluxrules
python examples/00_getting_started.py
```

**Problem:** Script runs but seems to hang

**Solution:** Some examples have long output. Check for recent output or press Ctrl+C.

### Python Version Issues

FluxRules requires Python 3.10+. Check your version:
```bash
python --version  # Should be 3.10 or higher
```

### Performance Issues

For help choosing the right engine and optimizing performance:
- See `examples/10_pluggable_engines.py` for engine comparison
- Check `docs/benchmarks.md` for detailed performance analysis
- Review `docs/choosing-an-engine.md` for selection guidance

---

## 📚 Additional Resources

### Core Documentation
- **[Main README](../README.md)** - Project overview and features
- **[Quick Start](../docs/quickstart.md)** - 5-minute introduction
- **[Installation](../docs/installation.md)** - Setup guide

### Learning & Examples
- **[Examples Learning Path](../docs/examples.md)** - Structured guide through all examples
- **[Getting Started](../docs/GETTING_STARTED.md)** - Step-by-step tutorial

### Feature Guides
- **[Simple Conditions](../docs/conditions.md)** - Master operators
- **[Complex Conditions](../docs/complex-conditions.md)** - AND/OR logic  
- **[Domain & Tags](../docs/domains-and-tags.md)** - Organization at scale
- **[Working Memory](../docs/working-memory.md)** - Stateful evaluation
- **[Sessions & State](../docs/sessions.md)** - Long-running workflows
- **[YAML & CSV Rules](../docs/yaml-csv-rules.md)** - Rules as configuration
- **[Engine Comparison](../docs/engine-comparison.md)** - Engine selection
- **[REST API](../docs/rest-api.md)** - Microservice deployment
- **[Rule Builder](../docs/rule-builder.md)** - Fluent API

### Reference
- **[API Reference](../docs/api.md)** - Complete API documentation
- **[Architecture Guide](../docs/architecture.md)** - Design and internals
- **[Validation Framework](../docs/validation-framework.md)** - Built-in validation
- **[Performance Benchmarks](../docs/benchmarks.md)** - Performance analysis
- **[Deployment Guide](../docs/deployment.md)** - Production deployment
- **[Troubleshooting](../docs/troubleshooting.md)** - Common issues and solutions


---

## 🤝 Contributing

Found an issue in the examples? Help us improve!

1. **Verify the issue** - Run the example to confirm the problem
2. **Check the output** - Verify the output matches the description
3. **File an issue** - Include the example output and Python version
4. **Submit a PR** - Ensure all examples pass before submitting

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.

---

## � Example Statistics

- **Total Examples:** 17 (numbered 00-16)
- **Total Learning Time:** ~3 hours
- **Structure:** progressive learning groups
- **Operator Coverage:** All 10 FluxRules operators demonstrated
- **Real-World Use Cases:** 5+ (fraud, compliance, lending, DevOps, streaming)

---

**Happy Rule Building! 🎉**

Start with `00_getting_started.py` and progress at your own pace. All examples are self-contained and can run independently once you understand the basics.
