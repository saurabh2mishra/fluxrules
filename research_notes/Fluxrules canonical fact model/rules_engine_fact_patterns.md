# Rules Engine Fact Patterns: Multi-Source Facts and Canonical Fact Models

## How do production rules engines handle multi-source facts?

### Takeaway
Production rules engines converge on a single pattern: each source feeds a per-source adapter that translates data into the engine's native fact type, and all rules evaluate against a unified working memory that has no knowledge of where facts originated.

### Cited Findings
- **Drools entry points:** Drools partitions its working memory using named "entry points." Each entry point receives facts from one source. You obtain a handle with `getWorkingMemoryEntryPoint("my entry point")` and call `insert(fact)` through it. Entry points are most common in event-processing pipelines but available to any application. — [Drools 6.5 docs, ch07](https://docs.jboss.org/drools/release/6.5.0.CR2/drools-docs/html/ch07.html)
- **Drools fact insertion:** `insert()` returns a `FactHandle`; `update()` re-notifies the engine; `delete()` (previously `retract`) cancels active matches. Identity mode (default) uses `IdentityHashMap`; equality mode uses `equals()`/`hashCode()`. — [Drools 6.5 docs, ch07](https://docs.jboss.org/drools/release/6.5.0.CR2/drools-docs/html/ch07.html)
- **OPA / Rego — no fixed schema:** OPA's stated design principle is "OPA should adapt to data in the outside world, not the other way around." Callers serialize their own data to arbitrary JSON and send it as `input`; there is no OPA-specific transformation required. External world state is pushed separately. — [OPA Rego Design Principle 2](https://openpolicyagent.org/blog/rego-design-principle-2-embrace-hierarchical-data-8a4913bdfea1)
- **OPA — two fact streams:** `input` carries the immediate request (user, action, resource). Separately loaded external data carries slowly changing world state (cluster resources, permissions). The policy author navigates both documents; they are never merged by OPA. — [OPA Rego Design Principle 2](https://openpolicyagent.org/blog/rego-design-principle-2-embrace-hierarchical-data-8a4913bdfea1)
- **Clara (Clojure) — immutable working memory:** Clara's working memory is immutable and persistent. Each change yields a new memory that shares structure with the previous one. Facts are Clojure records or Java beans. Clara uses Rete internally. At ~5 million facts, users have reported OOM errors because Clara's working-memory structures add overhead on top of the facts. — [Clara GitHub README](https://github.com/coopsource/clara-rules); [clojurians-log discussions 2020–2021](https://clojurians-log.clojureverse.org/clara/2021-06-10)
- **Experta / PyKnow (Python):** Facts are declared as Python classes that subclass `Fact`, with typed fields. The engine lifecycle is `reset()` → `declare(MyFact(...))` → `run()`. Facts have been frozen by default since version 1.2.0; a `Fact.as_dict()` method was added in 1.4.0. — [Experta on PyPI](https://pypi.org/project/experta/1.9.3/)
- **durable_rules (Python):** Facts are plain Python dicts posted to a named ruleset. The engine uses a Rete network implemented in C. V2 removed the Redis state requirement; state is now evaluated fully in C. — [durable_rules on PyPI](https://pypi.org/project/durable_rules/0.33.98/)

### Inferences
- There are two poles: typed-fact engines (Drools, Experta) that require upfront schema definition, and schemaless engines (OPA, durable_rules) that accept arbitrary dicts/JSON. The choice is a design decision, not an engine limitation.
- Entry points (Drools) are effectively named channels into working memory — a lightweight source-tagging mechanism that does not require facts from different sources to be different types.

### Gaps
- No source found for how the current Drools 8.x / Kogito handles multi-source facts; the references are all Drools 5–6.

---

## What is the "working memory" or "fact store" pattern and how does it decouple fact source from rule evaluation?

### Takeaway
Working memory is the central, engine-managed collection of currently asserted facts. Rules evaluate against it exclusively; rule logic has no direct knowledge of how or where facts were fetched. This gives a clean boundary: source adapters handle I/O and translation, and the engine handles inference.

### Cited Findings
- **Two-phase evaluation in Drools:** The engine alternates between a Working Memory Actions phase (insert, update, delete) and an Agenda Evaluation phase (rule selection and firing). `fireAllRules()` should be called after all facts are inserted, not interleaved with insertion. — [Drools 6.5 docs, ch07](https://docs.jboss.org/drools/release/6.5.0.CR2/drools-docs/html/ch07.html)
- **Lazy propagation by default (PHREAK):** Under Drools' PHREAK algorithm, rule evaluation is lazy by default. `@Propagation(IMMEDIATE)` or `EAGER` annotations force earlier propagation. — [Drools 6.5 docs, ch07](https://docs.jboss.org/drools/release/6.5.0.CR2/drools-docs/html/ch07.html)
- **Event listeners for auditing:** `WorkingMemoryEventManager` allows attaching listeners for `ObjectInsertEvent`, `ObjectUpdatedEvent`, `ObjectDeletedEvent`, `MatchCreatedEvent`, and `AfterMatchFiredEvent`. `DebugRuleRuntimeEventListener` prints events for debugging. — [Drools 6.5 docs, ch07](https://docs.jboss.org/drools/release/6.5.0.CR2/drools-docs/html/ch07.html)
- **Clara's immutable memory:** Clara's persistent working memory means the original session object is unchanged by inserts; evaluation reads a snapshot. This separation is a structural decoupling between mutation and evaluation. — [Clara GitHub README](https://github.com/coopsource/clara-rules)
- **Experta lifecycle:** `reset()` clears working memory; `declare()` populates it; `run()` fires rules. The source of facts (database query, file parse, API call) is entirely outside the engine. — [Experta on PyPI](https://pypi.org/project/experta/1.9.3/)
- **Vulcan (Latchfield):** This separate Python library explicitly describes its working memory as holding typed, immutable Fact objects with updates made by replacing facts rather than mutating them. (Separate from durable_rules.) — [Vulcan / Latchfield understanding-facts](https://latchfield.com/vulcan/docs/guides/understanding-facts/)

### Inferences
- For a small Python rules engine, working memory can be as simple as a list or dict of fact objects. The important invariant is that rules read from it but never call back to the original data source.
- The event-listener pattern (ObjectInsertEvent etc.) is worth replicating for observability in fluxrules, even if the initial version uses simple callbacks.

### Gaps
- No sources found comparing working memory implementations at scale for Python-specific engines (memory layout, GIL contention, etc.).

---

## What is a "fact adapter" or "fact loader" pattern — is there a common interface across sources?

### Takeaway
The canonical pattern uses two interfaces: a **FactCreator** (batch, for testing and one-shot loads) and a **FactRetriever** (incremental, for long-term and slowly-changing facts). Both call the engine's `Assert()` / `insert()` method; the engine doesn't know about the source.

### Cited Findings
- **Microsoft Logic Apps / BizTalk Rules Engine:** The `IFactCreator` interface has two methods: `CreateFacts(RuleSetInfo)` returning `object[]` and `GetFactTypes(RuleSetInfo)` returning `Type[]`. It is used for testing and batch loads. — [Azure Logic Apps Rules Engine docs](https://learn.microsoft.com/en-us/azure/logic-apps/rules-engine/build-fact-creators-retrievers)
- **IFactRetriever interface:** `UpdateFacts(RuleSetInfo, RuleEngine, object factsHandleIn)` is called at every execution cycle. The `factsHandleIn` object is `null` on the first call, then reused as a token; the retriever uses it to decide whether to refresh. The example asserts both .NET POJOs and XML documents via `engine.Assert(...)`. An optional `IFactRemover` interface handles post-execution cleanup (committing DB changes, retracting stale facts). — [Azure Logic Apps Rules Engine docs](https://learn.microsoft.com/en-us/azure/logic-apps/rules-engine/build-fact-creators-retrievers)
- **Per-source adapter (patent):** A 2001 patent describes a rule engine adapter that maps premise facts into the engine's API and maps derived facts back out. Each rule set gets its own adapter generated by a factory. The common interface is `executeRules(facts[]) → derivedFacts[]`. — [US Patent 20010029499, Justia](https://patents.justia.com/patent/20010029499)
- **Fact type abstraction (patent):** A second patent abstracts fact types (plain text, XML, database tables, POJOs, CSV) behind an object type API between the engine core and working memory. This lets the engine treat facts uniformly without converting them to a single native type. — [US Patent 7991727, Justia](https://patents.justia.com/patent/20090216702)
- **Separation of long-term vs. request-time facts:** The IFactRetriever pattern caches long-term facts across multiple execution cycles rather than re-fetching them every time. This is distinct from per-request input. — [Azure Logic Apps Rules Engine docs](https://learn.microsoft.com/en-us/azure/logic-apps/rules-engine/build-fact-creators-retrievers)

### Inferences
- For fluxrules, the IFactRetriever pattern suggests a clean interface: `load(context) -> List[Fact]` where `context` carries the minimal info (e.g. entity id, timestamp) needed to fetch facts, plus a `needs_refresh(handle)` predicate for caching.
- Separating "long-term / slow facts" (reference data, config) from "per-evaluation facts" (the current event or record under evaluation) is architecturally valuable and maps well to a Python design with a FactLoader base class.

### Gaps
- No Python-native examples of the IFactRetriever/IFactCreator pattern found; all sources are C# / Java. The translation to Python idioms (protocol, ABC, or duck typing) is a design decision left to fluxrules.

---

## How do engines handle schema evolution (new fields, renamed fields, missing fields)?

### Takeaway
There is no single standard; most engines rely on one or more of: immutable fact versions (with effective-date ranges), dynamically addressed/optional fields, or the engine owner's convention for deprecation. Schemaless dict-based approaches naturally absorb new fields without code changes.

### Cited Findings
- **Immutable rule versioning:** A practitioner guide recommends each versioned rule carry an extra condition specifying the valid time period. Each change publishes the next immutable version; nothing is edited or deleted. Rules keep a stable UUID across versions. — [BRCommunity Rule History and Versioning Part 1](https://www.brcommunity.com/articles.php?id=b375); [Laravel rules-engine package on Packagist](https://packagist.org/packages/leeovery/rules-engine)
- **Dynamically addressable facts to avoid recompilation:** A patent cites a real-world problem: rolling out even simple data model changes that require code modification can cause weeks or months of delays. Its solution makes input and output fields dynamically addressable by string name so new facts don't require recompiling code. — [US Patent 8856058, USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8856058)
- **Schema evolution vs. schema versioning distinction:** A data-warehouse survey distinguishes these two: evolution migrates old data to the new schema; versioning keeps all historical schemas by temporal extension or physical storage of multiple versions. — [ArXiv: A Survey on Data Warehouse Evolution (1012.1565)](https://arxiv.org/pdf/1012.1565)
- **OPA: no fact schema at all.** OPA imposes no schema on `input` or external data. New fields are simply navigated in Rego using dot or bracket access; missing fields return `undefined` (which evaluates as falsy). The policy handles absence by convention. — [OPA Rego Design Principle 2](https://openpolicyagent.org/blog/rego-design-principle-2-embrace-hierarchical-data-8a4913bdfea1)
- **Pydantic's model_validator(mode='before') for pre-validation normalization:** A 2026 Pydantic tutorial shows how to rename or reshape fields before validation runs, which enables a migration adapter that accepts both old and new field names. — [Pydantic custom validators, 2026](https://oneuptime.com/blog/post/2026-01-25-custom-validators-pydantic-v2/view)

### Inferences
- For a Python rules engine, the simplest path is: use Pydantic models with `Optional` fields and `model_validator(mode='before')` for aliasing. New fields are additive (no breakage). Renamed fields get a pre-validator alias.
- Long-term, a versioned fact type registry (fact class name + version int) allows running old rules against old schemas while new rules use new schemas. This is worth designing for from day one, even if V1 only supports a single version.

### Gaps
- No source found on how Drools or other JVM engines handle in-flight schema migration for already-asserted facts when the fact class changes between sessions.

---

## What is the tradeoff between a typed/schema-validated fact model vs a schemaless dict-based one?

### Takeaway
Typed models (Pydantic, dataclasses) provide IDE completion, early error detection, and self-documenting contracts at the cost of upfront schema definition and migration overhead. Schemaless dicts are flexible and absorb schema changes without code changes, but move all validation errors to rule-evaluation time, often with less helpful messages.

### Cited Findings
- **Pydantic v2 performance:** The Pydantic v2 validation core is written in Rust (`pydantic-core`), making it among the fastest validation libraries for Python. Strict mode disables implicit coercion. — [pydantic-core GitHub](https://github.com/martinabeleda/pydantic-core); [pydantic.dev why](https://docs.pydantic.dev/dev/why)
- **Dataclass vs Pydantic:** Plain Python dataclasses provide structure but no runtime validation, no JSON Schema generation, and no serialization. Pydantic adds all three to the same type-annotated syntax. — [ADR-004 data validation, cleverthis.com](https://git.cleverthis.com/HAL9000/temp/raw/branch/feature/git-worktree-apply/docs/adr/ADR-004-data-validation.md)
- **Complex model debugging cost:** Nested Pydantic models with custom validators can be difficult to debug when validation fails deep in the hierarchy. `model_construct()` bypasses validation for hot paths (decision tree traversal), but must be used with explicit justification. — [ADR-004 data validation, cleverthis.com](https://git.cleverthis.com/HAL9000/temp/raw/branch/feature/git-worktree-apply/docs/adr/ADR-004-data-validation.md)
- **durable_rules uses plain dicts:** Facts and events are plain Python dicts. No schema enforcement. The engine is optimized for throughput. — [durable_rules on PyPI](https://pypi.org/project/durable_rules/0.33.98/)
- **Experta uses typed Facts:** Facts inherit from `Fact`, fields are type-annotated, and fact values are frozen by default. The pattern enables safe pattern-matching in rule conditions. — [Experta on PyPI](https://pypi.org/project/experta/1.9.3/)
- **Pydantic in retrack (Python rules engine):** The `retrack` rules engine uses Pydantic to generate and validate its `request_model` (the expected input schema for a rule), providing a typed contract per rule. — [retrack on PyPI](https://pypi.org/project/retrack)

### Inferences
- A pragmatic middle ground for fluxrules: use Pydantic `BaseModel` as the canonical fact type (typed, validated, serializable), but accept plain dicts as input and normalize them to Pydantic models at the source-adapter boundary. This confines schemalessness to the adapter layer and keeps the rule-evaluation layer typed.
- `model_construct()` is the escape hatch for performance-sensitive paths once the schema is trusted (e.g., facts loaded from a pre-validated Parquet file).

### Gaps
- No benchmark comparing Pydantic fact validation overhead vs. dict-based fact access at realistic rules-engine scale (thousands of facts evaluated per second) was found. This matters for fluxrules if it targets streaming or high-throughput use cases.

---

## Are there lightweight Python libraries providing a canonical data model across Parquet, Avro, databases, and streaming?

### Takeaway
Apache Arrow provides the canonical in-memory columnar format that most Python data tools already support, making it the lowest-friction common representation. Ibis provides a unified query API over 20+ backends, so facts can be loaded from diverse sources with a single consistent interface. Neither replaces schema validation; Pydantic fills that role.

### Cited Findings
- **Apache Arrow overview:** Arrow is "a standardized, language-agnostic specification for representing structured, table-like datasets in-memory." Systems exchange Arrow data "at little-to-no cost" because they share the same memory layout, avoiding serialization. Arrow supports a rich type system including nested and user-defined types. — [arrow.apache.org/overview](https://arrow.apache.org/overview/)
- **Arrow's role:** Arrow standardizes memory representation. Any normalization of field names, types, or semantics across sources must be done by the pipeline before or after data lands in Arrow. Arrow itself is not a schema-mapping or cleansing tool. — [Apache Arrow deep dive, tributarydata.substack.com](https://tributarydata.substack.com/p/apache-arrow-the-missing-deep-dive)
- **Ibis unified dataframe API:** Ibis provides one API that runs against 20+ backends including DuckDB, PostgreSQL, BigQuery, Snowflake, Polars, and PySpark. Code written once can run on any supported backend. The default local engine is DuckDB. — [Ibis on dev.co](https://dev.co/databases/open-source/ibis); [ibis-framework on PyPI](https://pypi.org/project/ibis-framework/8.0.0/)
- **Ibis execution model:** Ibis uses deferred execution, pushing work to the query engine. This means a fact-loading query written in Ibis can target Parquet (via DuckDB), a live Postgres table, or a BigQuery dataset with no code changes. — [Ibis backends docs, tessl.io](https://tessl.io/registry/tessl/pypi-ibis-framework/files/docs/backends.md)
- **Pydantic as schema layer:** Pydantic v2 (`model_validator(mode='before')`) can normalize raw dicts before field validation — renaming fields, parsing strings into typed values, or populating defaults. It integrates with Arrow via PyArrow's `to_pydict()` conversion. — [Pydantic custom validators, oneuptime.com](https://oneuptime.com/blog/post/2026-01-25-custom-validators-pydantic-v2/view); [pydantic.dev why](https://docs.pydantic.dev/dev/why)

### Inferences
- A practical fluxrules stack for multi-source facts: **Ibis** to load/query from any backend → **PyArrow RecordBatch or Table** as the in-memory canonical format for batch fact loading → **Pydantic** to validate and name-normalize individual fact rows before inserting into the engine's working memory.
- For small datasets and simple pipelines, the Arrow intermediate step can be skipped; Ibis can produce Python dicts directly and Pydantic validates them.

### Gaps
- No source confirms that Ibis has reached API stability for all 20+ backends as of late 2025/2026. Some backends may lag. Check the Ibis changelog before committing to a specific backend.
- No source found on Arrow's schema metadata or provenance tracking (whether Arrow records which source a column came from). This is relevant if fluxrules needs to tag facts with their source.

---

## What does "fact normalization" look like in practice?

### Takeaway
Fact normalization consists of three operations applied at the adapter layer: (1) flattening nested structures to a single level, (2) aliasing or renaming fields to a canonical name, and (3) handling nulls and missing values with explicit defaults. None of the major rules engines handle this internally; it is the caller's responsibility.

### Cited Findings
- **Recursive flattening in Python:** A common approach joins the key path with a separator so a nested path becomes one flat key (e.g., `address.city` → `address_city`). The approach raises an error on duplicate keys and silently drops empty lists and dicts, so distinct inputs can collapse to the same output. — [Flattening Nested Objects in Python, skeptric.com](https://skeptric.com/flatten-object-python/)
- **pandas json_normalize:** `pd.json_normalize` recursively flattens nested dicts, joins key names with `.` by default, and expands arrays with `record_path` and `meta` options. `max_level` and `sep` control depth and separator. — [DEV Community json_normalize article](https://dev.to/dotnetdev/lateral-flattening-of-json-data-in-python-5he2); [GeeksforGeeks pandas flatten JSON](https://geeksforgeeks.org/python-pandas-flatten-nested-json)
- **Field aliasing via projection:** The MongoDB guide shows selecting a nested field and assigning it a top-level name in a projection, which is equivalent to aliasing (`address.city` → `city`). — [OneUptime MongoDB flatten doc](https://oneuptime.com/blog/post/2026-03-31-mongodb-flatten-document-nested-objects/markdown)
- **Pydantic pre-validation normalization:** `model_validator(mode='before')` can rename fields (aliasing old → canonical names) before field-level validation runs. This is the cleanest Python pattern for handling both old and new field names in one model. — [Pydantic custom validators, oneuptime.com](https://oneuptime.com/blog/post/2026-01-25-custom-validators-pydantic-v2/view)
- **OPA's approach:** OPA leaves normalization to the caller. The policy navigates whatever structure arrives via dot/bracket access. Missing fields return `undefined`. Convention rather than validation governs field naming. — [OPA Rego Design Principle 2](https://openpolicyagent.org/blog/rego-design-principle-2-embrace-hierarchical-data-8a4913bdfea1)

### Inferences
- For fluxrules, fact normalization should live in the source adapter, not the engine core. A `FactNormalizer` helper (or base class method) with three pluggable steps — flatten, alias, fill_defaults — keeps the engine clean and makes normalization testable in isolation.
- Using `pd.json_normalize` is viable for batch loads; for streaming or single-record cases, a recursive dict-flatten utility plus a Pydantic model with field aliases is a lighter and more idiomatic approach.
- The risk of information loss in flattening (empty collections, ambiguous separator collisions) is real and should be documented as a constraint of the canonical fact model.

### Gaps
- No source found on rules-engine-specific normalization libraries for Python. The existing literature treats normalization as a generic data engineering problem, not a rules-engine concern. fluxrules would be pioneering this integration.
