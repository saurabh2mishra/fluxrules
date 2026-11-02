# FluxRules

FluxRules is a lightweight Python library for defining, checking and
evaluating business rules. You write a rule once, and FluxRules tells you
which rules match a piece of data and which actions they ask for. The engine
is PHREAK, a fast and deterministic matching algorithm inspired by the one in
Drools.

```python
from fluxrules import F, Rule, evaluate

rule = Rule(name="big_payment", conditions=F("amount") > 1000, action="review")

result = evaluate(rule, {"amount": 4200})
print(result.actions)  # ['review']
```

## What you can do

- **Write rules in Python or as data.** Build conditions with `F` expressions,
  a step-by-step builder, plain dictionaries or YAML files. See
  [Authoring Rules](authoring-rules.md).
- **Combine checks freely.** Nest AND, OR and NOT as deep as you need. See
  [Complex Conditions](complex-conditions.md).
- **Organize rules.** Group rules by domain and tag, and give them priorities
  that set the order in which they fire. See
  [Domains and Tags](domains-and-tags.md).
- **Catch mistakes early.** Validate rules before they run, and check every
  field a rule uses against a typed model. See
  [Validation Framework](validation-framework.md) and
  [Typed Facts](typed-facts.md).
- **Evaluate facts in the way that suits you.** Use one call, an engine, a
  batch spread across CPU cores, a stream of updates, a session, the command
  line or HTTP. See [Ways to Evaluate a Fact](evaluating-facts.md).
- **Prepare messy input.** Flatten, rename, convert and enrich raw data before
  it reaches the engine. See [Fact Pipeline](fact-pipeline.md).
- **Act on the result.** Every result names the rules that fired, the actions
  they ask for and how long evaluation took. Register handlers to run those
  actions. See [Actions](custom-actions.md).
- **Extend it.** Plug in your own engine, transforms and actions. See
  [Extension Points](extension-points.md).

[Advanced Capabilities](advanced-capabilities.md) maps every advanced feature
to its guide and to a runnable example.

## What this project covers

- A Python library that runs inside your own process.
- An optional HTTP server, database storage, metrics and tracing, each
  installed as an extra.
- Runnable examples in the `examples/` folder and a large test suite.

It does not include a hosted service. The package source lives in
`src/fluxrules`.

## Where to start

1. [Installation](installation.md): install the package and any extras.
2. [Quickstart](quickstart.md): write and evaluate your first rules.
3. [Concepts](concepts.md): learn the words the rest of these docs use.
4. [From Fact to Action](fact-to-action.md): follow one fact through every
   stage of evaluation.
5. [Ways to Evaluate a Fact](evaluating-facts.md): pick how your application
   sends facts to the engine.
