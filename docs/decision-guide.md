# Decision Guide

**Prerequisites:** All [Concepts](concepts.md).

---

High-level flowchart for FluxRules usage decisions.

## Is FluxRules right for your use case?

**Do you need to:**
- Execute business rules conditionally? (Yes → continue)
- Match complex logic against data? (Yes → continue)
- Change rules without code deployment? (Yes → continue)

**If all yes:** FluxRules is a good fit.

## Integration: Library vs API?

**Library mode** (in-process):
- Import FluxRules in your app
- Evaluate locally
- No network overhead
- Single deployment unit

```python
from fluxrules import Rule
from fluxrules.engine.phreak import PhreakEngine

engine = PhreakEngine()
rule = Rule(
    name="adult",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    action="allow",
    persist=False,
)
engine.load_rules([rule])
fact = {"age": 21}
result = engine.evaluate(fact)
```

**API mode** (microservice):
- Run FluxRules as separate service
- Evaluate via HTTP
- Network latency added
- Separate deployment and scaling

```bash
curl -X POST http://fluxrules-service/api/v1/evaluate \
  -d '{"facts": {...}}'
```

**Decision:**
- Single app, fast iteration → Library
- Multiple services, shared rules → API
- High scale requirements → API

## Persistence: Store rules or keep in-memory?

**In-memory (default):**
- Rules defined in code
- No database needed
- Rules reset on app restart

```python
# python skip
engine.load_rules([rule1, rule2, ...])
```

**Persistent (database):**
- Rules stored in database
- Load rules on startup
- Audit trail available
- Requires `[sql]` extra

```bash
export DATABASE_URL=postgresql://...
service.persist_rules([rule1, rule2, ...])
```

**Decision:**
- Prototype/testing → In-memory
- Production/stable rules → Persistent
- Rules change frequently → Persistent

## State management: Stateless or stateful?

**Stateless (each evaluation independent):**
- Default behavior
- No side effects between evaluations
- Simple, predictable

```python
# python skip
result1 = engine.evaluate(fact1)
result2 = engine.evaluate(fact2)  # No state from result1
```

**Stateful (multi-step workflow with sessions):**
- Accumulate facts across evaluations
- Session snapshot support
- Requires `[sql]` extra

```python
# python skip
session.add_fact("step1", value)
session.evaluate()
session.add_fact("step2", value)
session.evaluate()
```

**Decision:**
- Single fact evaluation → Stateless
- Multi-step workflow → Stateful

---

## Next Steps

- **Concepts** — See [Concepts](concepts.md) for fundamentals
- **Quickstart** — See [Quickstart](quickstart.md) for hands-on
- **Architecture** — See [Architecture](architecture.md) for detailed design
