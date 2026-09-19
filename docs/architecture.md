# Architecture

**Prerequisites:** [Concepts](concepts.md).

---

FluxRules is a lightweight rule evaluation engine with a clean layered architecture. This page describes the system design from the DSL down to engine execution.

## System Architecture

```
┌──────────────────────────────────────────────────┐
│          Your Application Code                   │
│       (Rules, Facts, Actions, Workflows)         │
└──────────────────────┬───────────────────────────┘
                       │
        ┌──────────────▼──────────────—┐
        │   Public API (fluxrules)     │
        │  ┌──────────────────────┐    │
        │  │ Rule (Pydantic v2)   │    │
        │  │ - condition_dsl      │    │
        │  │ - action             │    │
        │  │ - domain, tags       │    │
        │  └──────────────────────┘    │
        └──────────────┬───────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │   Evaluation Engine             │
        │  ┌────────────┬────────────┐    │
        │  │  Stateless │  Streaming │    │
        │  │  (default) │  (opt-in)  │    │
        │  └────────────┴────────────┘    │
        │   PHREAK engine                 │
        │  → EvaluationResult             │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │   Infrastructure                │
        │  ┌────────────────────────┐     │
        │  │ DSL Validation         │     │
        │  │ Working Memory         │     │
        │  │ Field Index            │     │
        │  │ ActionRegistry         │     │
        │  │ FactPipeline           │     │
        │  └────────────────────────┘     │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │   Services (Optional)           │
        │  ┌────────────────────────┐     │
        │  │ RuleService (CRUD)     │     │
        │  │ EvaluationSession      │     │
        │  └────────────────────────┘     │
        └─────────────────────────────────┘
```

---

## Evaluation Flow: From Fact to Result

### Single Fact Evaluation (Simple API)

```
User: engine.evaluate({"amount": 5000, "country": "NG"})
  │
  ├─→ [1. Validate fact structure]
  │
  ├─→ [2. Iterate loaded rules]
  │    (via the PHREAK network)
  │
  ├─→ [3. For each rule:
  │       - Evaluate condition_dsl against fact
  │       - If matched: add to fired_rules list
  │       - If matched & action exists: execute action
  │
  ├─→ [4. Collect results]
  │    - fired_rules: List[int] (matched rule IDs)
  │    - actions: List[Any] (action results)
  │    - latency_ms: float (execution time)
  │
  └─→ EvaluationResult(fired_rules=[1, 3], actions=["flag"], latency_ms=0.45)
```

### Multi-Step Workflow (Session-Based)

```
User: session = service.create_session()
  │
  ├─→ [1. Add facts incrementally]
  │    session.add_fact("user_type", "premium")
  │    session.add_fact("amount", 10000)
  │
  ├─→ [2. Evaluate against accumulated facts]
  │    result = session.evaluate()
  │
  ├─→ [3. Session remembers state (optional)]
  │    - Save snapshot for recovery
  │    - Restore in another process
  │
  └─→ EvaluationResult (same structure as simple API)
```

---

## The Engine: PHREAK

**For evaluation modes and selection guidance**, see [The FluxRules Engine](engine-comparison.md) and [Choosing an Evaluation Mode](choosing-an-engine.md).

### PHREAK (Phased Evaluation and Knowledge—the single engine)

**Data flow:**
```
Load rules → [Store rules list]
              ↓
Fact input → [Linear iteration over rules]
              ├→ For each rule: evaluate condition
              ├→ Match? Add to results
              ↓
          [Produce EvaluationResult]
          ↓
          [Discard working memory for next fact]
```

**Stateless mode (default):**
- Most HTTP/stateless workloads
- Rules added/removed frequently
- Low memory footprint required
- Single-fact evaluation (typical)

---

### Streaming mode (opt-in)

**Data flow:**
```
Load rules → [Build PHREAK network]
              ↓
Fact input → [Assert into working memory]
              ├→ Match new/changed facts
              └→ Report fired delta
              ↓
          [Produce EvaluationResult]
          ↓
          [Working memory persists across calls]
```

**When to use:**
- Many facts over same rule set within a session
- Event streams where only changes matter
- Incremental fact updates (assert/retract)

---

## DSL Processing Pipeline

The condition_dsl is a recursive JSON structure that's validated, compiled, and executed:

```
Input DSL:
{
  "type": "group",
  "op": "AND",
  "children": [
    {"type": "condition", "field": "amount", "op": ">", "value": 5000},
    {"type": "condition", "field": "country", "op": "in", "value": ["NG", "US"]}
  ]
}
  │
  ├─→ [1. Parse & Validate]
  │    - Check syntax (type, op, field names)
  │    - Ensure operator is valid (==, !=, <, >, in, contains, etc.)
  │
  ├─→ [2. Convert to AST]
  │    - Build tree of condition nodes
  │    - Resolve operator functions
  │
  ├─→ [3. Evaluate against fact]
  │    - Traverse AST
  │    - Apply operators to fact values
  │    - Short-circuit AND/OR when possible
  │
  └─→ boolean result (True = rule fires)
```

---

## Data Model: Rule

```python skip
Rule(
    name="high_value_payment",           # Identifier
    domain="fraud_detection",             # Grouping
    tags=frozenset(["tier_1", "urgent"]), # Cross-cutting labels
    priority=10,                          # Execution order (higher first)
    condition_dsl={...},                  # The DSL above
    action="flag_for_review",             # Or callable
    persist=False                         # Optional: store in database
)
```

**Key design:**
- Rule is immutable once created (frozen Pydantic model)
- Conditions are pure predicates (no side effects)
- Actions are simple strings or callables
- Domain/tags allow flexible rule organization

---

## Pluggability Points

FluxRules allows extension at three key layers:

### 1. Custom Engines
```python skip
class MyEngine(BaseEngine):
    def load_rules(self, rules: List[Rule]) -> None: ...
    def evaluate(self, fact: Dict) -> EvaluationResult: ...
```

### 2. Custom Actions
```python skip
@action(name="email_alert", category="notifications")
def email_alert(recipient: str, subject: str) -> bool:
    send_email(recipient, subject)
    return True
```

### 3. Custom Transforms (FactPipeline)
```python skip
class UpperCase(Transform):
    def apply(self, fact: Dict) -> Dict:
        return {k: v.upper() if isinstance(v, str) else v for k, v in fact.items()}
```

---

## Deployment Layers

### Standalone (Single Process)
```
┌──────────────────────┐
│  Your Application    │
│  ├─ PhreakEngine     │
│  └─ Rules            │
└──────────────────────┘
```

### Service-Based (HTTP)
```
┌──────────────────────┐
│  HTTP Client         │
│  └─ POST /evaluate   │
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│  FastAPI Server      │
│  ├─ RuleService      │
│  ├─ PhreakEngine     │
│  └─ Rules (database) │
└──────────────────────┘
```

### Distributed (Microservices)
```
┌──────────────────────┐     ┌──────────────────────┐
│  Rule Editor         │────▶│  Rule Repository     │
└──────────────────────┘     └──────────┬───────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────▼───────┐  ┌────────▼───────┐  ┌────────▼───────┐
            │  Engine Pod 1  │  │  Engine Pod 2  │  │  Engine Pod 3  │
            │  PhreakEngine  │  │  PhreakEngine  │  │  PhreakEngine  │
            │  (cached rules)│  │  (cached rules)│  │  (cached rules)│
            └────────────────┘  └────────────────┘  └────────────────┘
```

---

## Design Principles

1. **Evidence-first**: All documentation backed by working code
2. **Pydantic v2**: Rule validation via Pydantic (not home-grown)
3. **Pluggable**: Custom engines, actions, transforms via simple interfaces
4. **Fast**: Production-grade performance (ms-level latency)
5. **Simple**: Minimal API surface, small learning curve
6. **Lazy by default**: PHREAK's on-demand evaluation minimizes overhead

