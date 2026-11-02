# Custom Engines

**Prerequisites:** [Concepts](concepts.md) (Engine) and [Features](features.md).

---

FluxRules provides one standard engine: `PhreakEngine` (lazy, agenda-driven). You can implement a custom engine by subclassing `BaseEngine`.

## Why custom engines?

- **Specialized algorithms**: Implement domain-specific matching logic
- **Performance optimization**: Tailor to your data patterns
- **Integration**: Wrap external rule systems

## Custom engine structure

```python
from fluxrules.engine import BaseEngine
from fluxrules.domain import Rule
from fluxrules.domain.conditions.evaluator import evaluate_conditions
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
            if rule and evaluate_conditions(rule.conditions, facts):
                fired_ids.append(rule_id)
                actions.extend(rule.actions)
                explanations[rule_id] = f"Rule {rule.name} matched"
        return fired_ids, actions, explanations
```

## Using a custom engine

```python
from fluxrules import F

rule = Rule(
    name="high_value",
    conditions=F("amount") > 1000,
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

1. **Inherit from `BaseEngine`**: Provides working memory and utilities
2. **Return `EvaluationResult`**: Consistent result format
3. **Preserve the result contract**: Return fired IDs, actions, and explanations from `_evaluate_rules`
4. **Use `BaseEngine.evaluate()`**: It supplies discovery, filters, grouping, and latency measurement

## Evaluating many facts

Every engine gets `evaluate_batch(facts)` from `BaseEngine`. Without
`workers`, it calls your engine's `evaluate()` on each fact and returns the
results in order, so it works for a custom engine with no extra code:

```python
results = engine.evaluate_batch([{"amount": 5000}, {"amount": 10}])
assert [len(r.fired_rules) for r in results] == [1, 0]
```

`workers=N` (more than 1) runs the facts in `N` worker processes, and each
worker must build its own copy of your engine. `BaseEngine` cannot know how
to build yours, so by default it raises `NotImplementedError` and asks you to
use `workers=1`. To allow workers, override `_clone_settings()` and return
your engine class plus the keyword arguments its constructor needs:

```python
class BatchReadyEngine(MyCustomEngine):
    def __init__(self, threshold: int = 0) -> None:
        super().__init__()
        self.threshold = threshold

    def _clone_settings(self) -> tuple[type, dict[str, Any]]:
        return type(self), {"threshold": self.threshold}


assert BatchReadyEngine(threshold=5)._clone_settings() == (BatchReadyEngine, {"threshold": 5})
```

Each worker then calls `BatchReadyEngine(threshold=5)` and loads your rules
into it. The class and its arguments are sent to the workers by pickling, so
define the class at the top level of a module (not inside a function), and
call `evaluate_batch(facts, workers=4)` under `if __name__ == "__main__":`.
See [Many facts at once](usage/python-api.md#many-facts-at-once) for the
other rules that apply to workers.

---

## Next Steps

- **The FluxRules Engine**: See [The FluxRules Engine](engine-comparison.md) for the built-in PhreakEngine
- **Example**: See [Example 09: Custom Engines](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/09_custom_engines.py)
