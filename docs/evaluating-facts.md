# Ways to Evaluate a Fact

**Prerequisites:** [Concepts](concepts.md) (rules, facts, results).

---

A **fact** is the data you want to check, such as one payment:
`{"amount": 4200, "country": "DE"}`. **Evaluating** a fact means running your
rules against it and finding out which ones match.

FluxRules gives you several ways to do this. They all use the same rules and
the same matching logic, so the same fact always matches the same rules. They
differ in how the fact reaches the engine: one at a time, many at once, as a
stream, from the command line, or over HTTP.

This page shows each way with a small example and says when to use it. To see
what happens *inside* one evaluation, read [From Fact to Action](fact-to-action.md).

## The rules used on this page

Every example on this page uses these two rules:

```python
from fluxrules import F, Rule

RULES = [
    Rule(id=1, name="big_payment", conditions=F("amount") > 1000, action="review", priority=10),
    Rule(id=2, name="german_payment", conditions=F("country") == "DE", action="add_vat"),
]
FACT = {"amount": 4200, "country": "DE"}
```

`priority` decides the order of the results: higher numbers come first. The
fact above matches both rules, so the answer is always rule 1, then rule 2.

## What you get back

Most ways return an `EvaluationResult`. These are the fields you will use most:

| Field | What it holds |
|---|---|
| `fired_rules` | The ids of the rules that matched, highest priority first. This is the answer. |
| `actions` | The action names of the matched rules, in the same order. FluxRules does not run them; your code does. |
| `explanations` | One sentence per matched rule saying why it matched. |
| `rules_by_domain`, `rules_by_tag` | The matched rule ids grouped by each rule's `domain` and `tags`. |
| `latency_ms` | How long the evaluation took, in milliseconds. |

## Pick a way

| Way | Use it when | Keeps state between facts? |
|---|---|---|
| [1. `fluxrules.evaluate()`](#1-one-call-fluxrulesevaluate) | A script, a test, or a one-off check | No |
| [2. `engine.evaluate()`](#2-an-engine-engineevaluate) | Your application checks facts one by one. **The usual choice.** | No |
| [3. A model as the fact](#3-a-model-as-the-fact) | Your facts already have a Pydantic model or dataclass | No |
| [4. `engine.evaluate_batch()`](#4-many-facts-at-once-engineevaluate_batch) | You have a list of facts, such as rows from a table | No |
| [5. Streaming mode](#5-a-stream-of-updates-streaming-mode) | The same entity is sent again and again, and only changes matter | Yes |
| [6. `DedupEvaluator`](#6-repeated-facts-dedupevaluator) | Many facts are exact repeats | A cache of results |
| [7. `CrossFactEngine`](#7-facts-that-relate-to-each-other-crossfactengine) | A rule must compare two facts, such as a payment and its customer | Yes |
| [8. Sessions](#8-saved-rule-sets-and-sessions) | You build a fact up piece by piece, or save and restore it | Yes |
| [9. The command line](#9-the-command-line) | You want to try rules from a file, or check them in CI | No |
| [10. HTTP](#10-http) | Another service sends facts to a FluxRules server | No |

---

## 1. One call: `fluxrules.evaluate()`

```python
import fluxrules

result = fluxrules.evaluate(RULES, FACT)

assert result.fired_rules == [1, 2]
assert result.actions == ["review", "add_vat"]
```

`fluxrules.evaluate(rules, fact)` takes one rule or a list of rules, and one
fact. It prepares the rules, evaluates the fact, and returns the result.

**Use it when** you check a fact once: in a script, a notebook or a test.

**Avoid it when** you check many facts against the same rules. It prepares
the rules on every call. An engine (way 2) prepares them once.

It reads the process-wide engine settings
(`fluxrules.engine.configuration.get_config()`). To give it different
settings, use an engine instead.

## 2. An engine: `engine.evaluate()`

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
engine.load_rules(RULES)

result = engine.evaluate(FACT)
assert result.fired_rules == [1, 2]

result = engine.evaluate({"amount": 50, "country": "US"})
assert result.fired_rules == []
```

Create the engine once and load the rules once, when your application starts.
After that, `engine.evaluate(fact)` is cheap: `load_rules` builds indexes, so
each evaluation only looks at rules that can match the fact.

**Use it when** your application checks facts one by one, for example one
per web request. This is the usual choice. One engine can be shared by many
threads.

Related methods on the same engine:

- `engine.evaluate_by_domain(fact, ["tax"])` and
  `engine.evaluate_by_tags(fact, ["fraud"])` only consider rules in those
  domains or with those tags. See [Domains and Tags](domains-and-tags.md).
- `engine.evaluate(fact, strict_facts=True)` checks the shape of the fact
  first (a dict with string keys and flat values) and raises a clear error if
  it is wrong.

The engine's settings are fixed when you create it. It keeps its own copy of
the `EngineConfig` you pass (or of the process-wide one), so changing that
object later does not change the engine. See
[Configuration](usage/configuration.md#settings-are-fixed-when-the-engine-is-created).

## 3. A model as the fact

If your facts already have a model, pass an instance of it directly:

```python
from pydantic import BaseModel

from fluxrules.engine.phreak import PhreakEngine


class Payment(BaseModel):
    amount: float
    country: str


engine = PhreakEngine(fact_schema=Payment)
engine.load_rules(RULES)

result = engine.evaluate(Payment(amount=4200, country="DE"))
assert result.fired_rules == [1, 2]
```

The engine turns the model into a plain dict before it checks the rules. A
Pydantic model, a dataclass, an attrs class or a msgspec `Struct` all work,
with or without `fact_schema`.

`fact_schema=Payment` is optional. With it, `load_rules` checks that every
field a rule names exists in `Payment`, so a rule with a typo is refused when
it loads instead of quietly never matching.

The engine can also clean facts that arrive as dicts before it checks the
rules:

- `fact_pipeline=` reshapes each dict, for example to flatten it or fill in
  defaults. See [Fact Pipeline](fact-pipeline.md#using-pipelines-with-engines).
- `validate_facts="normalize"` validates each dict against `fact_schema` and
  converts values, so `"4200"` becomes `4200.0`. `on_invalid=` decides what
  happens to a fact that fails. See [Typed Facts](typed-facts.md).

These steps run in that order (pipeline, then validation) and apply to every
way on this page that uses an engine.

## 4. Many facts at once: `engine.evaluate_batch()`

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
engine.load_rules(RULES)

facts = [
    {"amount": 4200, "country": "DE"},
    {"amount": 50, "country": "US"},
    {"amount": 9000, "country": "FR"},
]
results = engine.evaluate_batch(facts)

assert [r.fired_rules for r in results] == [[1, 2], [], [1]]
```

`evaluate_batch(facts)` returns one result per fact, in the same order as the
input. On its own it does the same as `[engine.evaluate(f) for f in facts]`.

Add `workers=4` to spread the facts over 4 processes, so they use 4 CPU
cores:

```python
results = engine.evaluate_batch(facts, workers=4)
```

Each worker process builds a copy of your engine, with the same rules and
settings, so the results are exactly the same. Starting processes takes time,
so this pays off for thousands of facts, not for a few.

**Use it when** you have a list of facts, such as rows from a database table
or lines from a file.

[Many facts at once](usage/python-api.md#many-facts-at-once) explains the
rules for `workers` and shows how to evaluate rows from a database.

## 5. A stream of updates: streaming mode

```python
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine(streaming_mode=True)
engine.load_rules(RULES)

assert engine.evaluate(FACT).fired_rules == [1, 2]  # first time: full answer
assert engine.evaluate(FACT).fired_rules == []  # same fact again: skipped
changed = {**FACT, "amount": 10}
assert engine.evaluate(changed).fired_rules == [2]  # changed: evaluated again
```

`streaming_mode=True` makes the engine remember the previous fact. A fact
identical to the previous one is skipped and returns no matches. A changed fact
is evaluated again.

**Use it when** the same entity, such as an account, is sent again and again,
and you only care when something changes.

**Avoid it when** each fact is independent, such as one request per payment.
Because the engine remembers, one stream must always go to the same engine.
Splitting a stream between servers or processes gives wrong answers, which is
why `evaluate_batch` with `workers` refuses a streaming engine.

See [Choosing an Evaluation Mode](choosing-an-engine.md).

## 6. Repeated facts: `DedupEvaluator`

```python
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.runtime import DedupEvaluator, LRUDedupBackend

engine = PhreakEngine()
engine.load_rules(RULES)
dedup = DedupEvaluator(engine, backend=LRUDedupBackend(max_entries=10_000))

first = dedup.evaluate(FACT)  # evaluated by the engine
again = dedup.evaluate({"country": "DE", "amount": 4200})  # same content: from the cache

assert again.fired_rules == first.fired_rules == [1, 2]
assert (dedup.stats.hits, dedup.stats.misses) == (1, 1)
```

`DedupEvaluator` wraps an engine and remembers the result for each fact it has
seen. When the same fact arrives again, it returns the remembered result
without running the rules. Two dicts with the same keys and values count as the
same fact, whatever the order of their keys.

- `backend=LRUDedupBackend(max_entries=10_000)` keeps at most 10,000 results in
  memory and forgets the least recently used one when it is full. This is also
  the default backend (with 100,000 entries). `RedisDedupBackend` shares the
  cache between processes; it needs the `redis` extra.
- `dedup.stats` counts cache `hits` and `misses`.

A result from the cache is the original result object, so its `latency_ms` and
`execution_id` are those of the first evaluation.

**Use it when** your input repeats a lot, such as retried events or polling.
It needs a stateless engine: it refuses a streaming one. Call `dedup.clear()`
after you load new rules, or old answers stay in the cache.

## 7. Facts that relate to each other: `CrossFactEngine`

The ways above check **one fact at a time**. When a rule must compare two
facts, such as "a payment over 2000 from a customer whose account is less than
14 days old", use `CrossFactEngine`:

```python
from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule, Pattern

engine = CrossFactEngine()
engine.load_rules(
    [
        CrossFactRule(
            id=1,
            name="large_payment_from_new_account",
            action="manual_review",
            patterns=[
                Pattern("p", "Payment", constraints=[("amount", ">", 2000)]),
                Pattern(
                    "c",
                    "Customer",
                    constraints=[("account_age_days", "<", 14)],
                    joins=[("id", "==", "p", "customer_id")],
                ),
            ],
        )
    ]
)

engine.insert("Payment", {"customer_id": "c1", "amount": 4200})
delta = engine.insert("Customer", {"id": "c1", "account_age_days": 5})
assert [a.rule_name for a in delta.added] == ["large_payment_from_new_account"]
```

Each `Pattern` matches one type of fact. `constraints` compare a field with a
value. `joins` compare a field with a field of a fact matched by an earlier
pattern: here, the customer's `id` must equal the payment's `customer_id`.

The engine keeps every inserted fact. `insert`, `update` and `retract` each
return a `CrossFactDelta`, whose `added` and `removed` lists say which matches
appeared or disappeared because of that change. It does not return an
`EvaluationResult`.

See [Cross-Fact Rules](cross-fact-rules.md).

## 8. Saved rule sets and sessions

`RuleService` stores rule sets by name. A session collects a fact piece by
piece and evaluates it against one named rule set:

```python
from fluxrules.domain.models import Ruleset
from fluxrules.services.rule_service import RuleService

service = RuleService.create()
service.persist(
    Ruleset(
        group="payments",
        rules=tuple(rule.to_engine_rule(group="payments") for rule in RULES),
    )
)

session = service.create_session("payments")
session.add_fact("amount", 4200)
session.add_fact("country", "DE")
assert session.evaluate().fired_rules == [1, 2]

snapshot = session.save()  # a JSON string you can store and restore later
```

- `Ruleset(group="payments", ...)` names the rule set. `to_engine_rule(group=...)`
  converts each `Rule` to the stored form.
- `create_session("payments")` starts an empty session for that rule set.
- `add_fact(key, value)` adds one field. `session.evaluate()` checks all fields
  added so far.
- `save()` and `EvaluationSession.restore(snapshot, service)` let you pause and
  continue later.

`service.evaluate_ruleset("payments", fact)` evaluates a whole fact against a
stored rule set in one call, without a session.

`RuleService.create()` keeps rule sets in memory. Storing them in a database
needs the `sql` extra. See [Sessions](sessions.md) and
[Persistence](persistence.md).

## 9. The command line

With the `cli` extra installed, evaluate a fact from a JSON file against rules
in a JSON or YAML file:

```bash
fluxrules evaluate rules.yaml event.json
fluxrules evaluate rules.yaml event.json --format json
fluxrules evaluate rules.yaml event.json --schema models.py:Payment --validate-facts normalize
```

- `--format json` prints the matched rules and actions as JSON instead of a
  table.
- `--schema models.py:Payment` checks the rules against the `Payment` model
  first, and stops with exit code 1 if a rule names a field the model lacks.
- `--validate-facts normalize` also validates and converts the event against
  that model before evaluating it.

**Use it when** you want to try rules without writing code, or check rule
files in CI. See [CLI](cli.md).

## 10. HTTP

The FluxRules server (the `api` extra) evaluates facts sent as JSON:

```bash
curl -X POST http://localhost:8000/api/v1/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"facts": {"amount": 4200, "country": "DE"}, "ruleset_id": "payments"}'
```

- `facts` is the fact to evaluate.
- `ruleset_id` is optional. It picks a stored rule set; without it, all stored
  rules are used. `rule_ids` picks individual rules instead.

The response lists the matched rule ids as `matched_rules`, plus `actions` and
an `execution_id`. `POST /api/v1/evaluate/bulk` takes a list under `facts` and
returns one result per fact. A session can also collect facts over several
requests and evaluate them later with `POST /api/v1/sessions/{id}/evaluate`.

**Use it when** another service, possibly not written in Python, needs
answers. See [REST API](rest-api.md) and [Deployment](deployment.md).

---

## Next Steps

- **Inside one evaluation**: [From Fact to Action](fact-to-action.md)
- **Stateless or streaming**: [Choosing an Evaluation Mode](choosing-an-engine.md)
- **Facts with a model**: [Typed Facts](typed-facts.md)
- **Many facts and several cores**: [Many facts at once](usage/python-api.md#many-facts-at-once)
- **A runnable tour of these ways**: `examples/32_ways_to_evaluate.py`
