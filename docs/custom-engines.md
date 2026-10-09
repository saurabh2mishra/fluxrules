# Custom Engines

**Prerequisites:** [Concepts](concepts.md) (Engine) and [Features](features.md).

---

FluxRules provides one standard engine: `PhreakEngine` (lazy, agenda-driven). You can implement a custom engine by subclassing `BaseEngine`.

## Why custom engines?

- **Specialized algorithms** - Implement domain-specific matching logic
- **Performance optimization** - Tailor to your data patterns
- **Integration** - Wrap external rule systems

## Custom engine structure

```python
from fluxrules.engine import BaseEngine
from fluxrules.domain import Rule
from fluxrules.domain.dsl.evaluator import evaluate_dsl
from typing import Any


class MyCustomEngine(BaseEngine):
    """Custom rule evaluation engine."""

    def _evaluate_rules(
        self, rule_ids: list[int], facts: dict[str, Any]
    ) -> tuple[list[int], list[str], dict[int, str]]:
        """Evaluate discovered rules and return fired IDs, actions, explanations."""
        fired_ids = []
        actions = []
        explanations = {}
        for rule_id in rule_ids:
            rule = self.rule_repository.get(rule_id)
            if rule and evaluate_dsl(rule.condition_dsl, facts):
                fired_ids.append(rule_id)
                actions.extend(rule.actions)
                explanations[rule_id] = f"Rule {rule.name} matched"
        return fired_ids, actions, explanations
```

## Using a custom engine

```python
rule = Rule(
    name="high_value",
    condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 1000},
    action="review",
    persist=False,
)
engine = MyCustomEngine()
engine.load_rules([rule])

result = engine.evaluate({"amount": 5000, "country": "US"})
print(f"Matched: {result.fired_rules}")
```

## Required methods

| Method | Purpose |
|--------|---------|
| `load_rules(rules)` | Initialize engine with rules |
| `_evaluate_rules(rule_ids, facts)` | Evaluate discovered rule IDs and return fired IDs, actions, and explanations |
| `assert_fact(fact)` | Store fact in working memory |
| `retract_fact(fact_id)` | Remove fact from working memory |

## Standard interfaces

Your custom engine should:

1. **Inherit from `BaseEngine`** - Provides working memory and utilities
2. **Return `EvaluationResult`** - Consistent result format
3. **Preserve the result contract** - Return fired IDs, actions, and explanations from `_evaluate_rules`
4. **Use `BaseEngine.evaluate()`** - It supplies discovery, filters, grouping, and latency measurement

---

## Next Steps

- **The FluxRules Engine** - See [The FluxRules Engine](engine-comparison.md) for the built-in PhreakEngine
- **Example** - See [Example 09: Custom Engines](https://github.com/fluxrules/fluxrules/blob/main/examples/09_custom_engines.py)
