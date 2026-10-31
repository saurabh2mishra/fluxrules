# Complex Conditions

Combine multiple simple conditions using AND / OR / NOT logic.

**Prerequisites:** [Authoring Rules](authoring-rules.md) and [Conditions & Operators](conditions.md), which covers all
operators and the four authoring formats.

---

## AND Logic

All conditions must be true for the rule to fire.

```python
from fluxrules import F, Rule, PhreakEngine

rule = Rule(
    name="high_value_international",
    conditions=(F("amount") > 5000) & (F("country").not_in(["US", "CA", "GB"])),
    action="manual_review",
)

engine = PhreakEngine()
engine.load_rules([rule])

print(engine.evaluate({"amount": 6000, "country": "NG"}).fired_rules)   # [1]
print(engine.evaluate({"amount": 3000, "country": "NG"}).fired_rules)   # []
```

Dict equivalent (the wire format stored in YAML/DB):

```python
{
    "type": "group",
    "op": "AND",
    "children": [
        {"type": "condition", "field": "amount", "op": ">", "value": 5000},
        {"type": "condition", "field": "country", "op": "not_in", "value": ["US", "CA", "GB"]},
    ],
}
```

---

## OR Logic

At least one condition must be true.

```python
rule = Rule(
    name="risky_pattern",
    conditions=(
        (F("amount") > 5000)
        | (F("velocity_1h") >= 5)
        | (F("ip_risk_score") >= 80)
    ),
    action="block_payment",
)

engine = PhreakEngine()
engine.load_rules([rule])

print(engine.evaluate({"amount": 6000, "velocity_1h": 1, "ip_risk_score": 30}).fired_rules)   # [1]
print(engine.evaluate({"amount": 1000, "velocity_1h": 6, "ip_risk_score": 30}).fired_rules)   # [1]
print(engine.evaluate({"amount": 1000, "velocity_1h": 1, "ip_risk_score": 30}).fired_rules)   # []
```

---

## NOT Logic

The condition must be false.

```python
rule = Rule(
    name="unverified_high_value",
    conditions=(
        (F("amount") > 2000)
        & ~(F("email_domain").ends_with("trusted.com"))
    ),
    action="step_up_auth",
)

engine = PhreakEngine()
engine.load_rules([rule])

print(engine.evaluate({"amount": 3000, "email_domain": "gmail.com"}).fired_rules)    # [1]
print(engine.evaluate({"amount": 3000, "email_domain": "trusted.com"}).fired_rules)  # []
```

---

## Nested Logic

Combine AND, OR, and NOT for multi-part rules:

```python
rule = Rule(
    name="payment_risk_triage",
    conditions=(
        # 1. Large amount
        (F("amount") > 2000)
        # 2. High-risk country OR high IP risk
        & (
            (F("country").isin(["NG", "SN", "GH"]))
            | (F("ip_risk_score") >= 70)
        )
        # 3. New or unverified device/account
        & (
            (F("account_age_days") < 7)
            | (F("device_age_days") < 7)
        )
        # 4. NOT a trusted email domain
        & ~(F("email_domain").ends_with("trusted.example"))
    ),
    action="manual_review",
)
```

The F DSL reads as close to the logic description as you can get in Python.
The same tree in dict form grows by about 4× in line count, which is why
the F DSL is the recommended authoring format.

---

## Operator precedence

Python's `&` and `|` bind more tightly than `>`, `<`, `==`. Always wrap each
individual leaf in parentheses before composing:

```python
# python skip: the Wrong line deliberately raises to show the trap
# Correct: each leaf is parenthesised
(F("amount") > 2000) & (F("country") == "NG")

# Wrong: & binds before ==, raising a TypeError
F("amount") > 2000 & F("country") == "NG"
```

---

## Next steps

- **[Conditions](conditions.md)**: full operator reference and validation guide
- **[examples/02_complex_conditions.py](https://github.com/saurabh2mishra/fluxrules/blob/main/examples/02_complex_conditions.py)**: runnable examples
