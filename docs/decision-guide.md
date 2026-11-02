# Decision Guide

**Prerequisites:** [Concepts](concepts.md).

---

This page helps you make the first design choices for a project that uses
FluxRules. Each section asks one question and points to the page that covers
the answer in depth.

## Is FluxRules a good fit?

FluxRules fits well when you need to:

- decide what to do with a piece of data based on business rules,
- combine many checks with AND, OR and NOT,
- change or review those rules separately from the code that uses them.

If all three apply, read on.

## Library or HTTP service?

**As a library**, FluxRules runs inside your own Python process:

```python
from fluxrules import F, PhreakEngine, Rule

engine = PhreakEngine()
engine.load_rules([Rule(name="adult", conditions=F("age") >= 18, action="allow")])
result = engine.evaluate({"age": 21})
```

There is no network call and nothing extra to deploy.

**As an HTTP service**, FluxRules runs as its own server, and other services
send facts to it:

```bash
curl -X POST http://localhost:8000/api/v1/evaluate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"facts": {"age": 21}}'
```

Each call adds network latency, but many services can share one set of rules,
and you can scale the server on its own.

Choose the library for a single application or when latency matters most.
Choose the HTTP service when several services, possibly not written in
Python, must use the same rules. See [HTTP API](api.md) to start the server.

## Rules in code or in a database?

**In code** is the default. You build rules in Python, or load them from a
YAML file, every time the application starts. Nothing else is needed. See
[YAML Rules](yaml-rules.md) for keeping rules in files.

**In a database**, rules are saved once and loaded on startup, and several
processes can share them. This needs the `sql` extra. See
[Persistence](persistence.md) and [Rule Lifecycle](rule-lifecycle.md).

Start with rules in code while you prototype. Move them to a database when
rules change more often than you deploy, or when several processes must share
them.

## Independent facts or state across steps?

Most applications check each fact on its own: one payment, one order, one
request. Use the engine as it is; this is stateless mode, the default.

Some applications collect data over several steps, such as an onboarding flow
that learns one field at a time. For that, use a **session**: it gathers the
fields of one fact and evaluates them when you ask. A session lives in
memory, and you can save it as a JSON snapshot and restore it later. See
[Sessions](sessions.md).

If you process a long stream of updates and only care about what changed
since the last update, use streaming mode. See
[Choosing an Evaluation Mode](choosing-an-engine.md).

---

## Next Steps

- **Quickstart**: See [Quickstart](quickstart.md) to write your first rules
- **Ways to Evaluate a Fact**: See [Ways to Evaluate a Fact](evaluating-facts.md) for every way to send facts to the engine
- **Architecture**: See [Architecture](architecture.md) for how the parts fit together
