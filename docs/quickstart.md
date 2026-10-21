# Quickstart

Get your first rule working in 5 minutes.

**Prerequisites:** 
- Python 3.10+ with `pydantic>=2.8`
- [Installation](installation.md) complete

---

## Your First Rule

Create a Python script:

```python
from fluxrules import F, PhreakEngine, Rule

# Create a rule
rule = Rule(
    name="high_value_transaction",
    domain="fraud_detection",
    conditions=F("amount") > 5000,
    action="manual_review",
    priority=100,
)

# Create an engine and load the rule
engine = PhreakEngine()
engine.load_rules([rule])

# Evaluate a fact
fact = {"amount": 6000}
result = engine.evaluate(fact)

print(f"Matched rules: {result.fired_rules}")
print(f"Actions: {result.actions}")
```

**Output:**
```
Matched rules: [1]
Actions: ['manual_review']
```

---

## Complex Conditions (AND/OR/NOT)

Rules can have nested boolean logic:

```python
from fluxrules import F, PhreakEngine, Rule

rule = Rule(
    name="risky_payment",
    domain="fraud_detection",
    # & means all must hold, | means either suffices, ~ means must be false
    conditions=(
        (F("amount") > 2000)
        & ((F("country").isin(["NG", "SN"])) | (F("ip_risk_score") >= 70))
        & ~(F("verified_user") == True)
    ),
    action="block_payment",
    priority=100,
)

engine = PhreakEngine()
engine.load_rules([rule])

# This fact matches all conditions
fact = {"amount": 3000, "country": "NG", "verified_user": False}
result = engine.evaluate(fact)
print(result.fired_rules)  # [1]
```

---

## Multiple Rules

Load multiple rules at once:

```python
from fluxrules import F

rules = [
    Rule(
        name="high_value",
        conditions=F("amount") > 5000,
        action="manual_review",
        priority=100,
    ),
    Rule(
        name="high_risk_country",
        conditions=F("country").isin(["NG", "SN"]),
        action="block_payment",
        priority=110,
    ),
]

engine = PhreakEngine()
engine.load_rules(rules)

fact = {"amount": 3000, "country": "NG"}
result = engine.evaluate(fact)

print(f"Matched: {result.fired_rules}")  # [2] (high_risk_country)
print(f"Actions: {result.actions}")       # ['block_payment']
```

---

## Learn More

- **[Concepts](concepts.md)** - Understanding Rule, Engine, Fact, Domain, Tag
- **[Conditions](conditions.md)** - All available operators
- **[Complex Conditions](complex-conditions.md)** - Nested AND/OR/NOT logic
- **[Domains & Tags](domains-and-tags.md)** - Organizing rules
- **[Examples](examples.md)** - Full working examples (31 files)

---

## Next: Try the Full Learning Path

All examples use a shared payment-risk dataset:

```bash
cd examples
python 00_getting_started.py    # ~2 min
python 02_complex_conditions.py # ~2 min
python 10_pluggable_engines.py  # ~2 min
```

See [examples.md](examples.md) for the complete 30-minute learning path.

