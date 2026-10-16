# Canonical Fact Model: Multi-Source Adapter Design for a Python Rules Engine

## Minimal FactSource Interface

### Takeaway
A minimal FactSource adapter needs only two core methods — a synchronous `load() -> dict | list[dict]` for batch sources and an `__iter__` or `stream() -> Iterator[dict]` for streaming ones — with async variants (`aload`, `astream`) added only when the calling rules engine already operates in an async context.

### Cited Findings
- Python's `typing.Protocol` enables structural subtyping so adapter classes do not need to inherit from a shared base class; a class satisfies the protocol if it has the right methods, making third-party sources easier to adapt — [oneuptime.com – Python Protocol Classes for Type Safety](https://oneuptime.com/blog/post/2026-02-02-python-protocol-classes-type-safety/markdown)
- ABCs are preferable when shared concrete methods (validation, logging, connection lifecycle) are needed across all adapters, while Protocols are preferable for lightweight contracts across module or package boundaries — [stanza.dev – Python Architecture Protocols vs ABC](https://www.stanza.dev/courses/python-architecture/protocols/python-architecture-protocols-vs-abc)
- Combining both is viable: use an ABC for the internal implementation hierarchy (shared connection teardown, error wrapping) and expose a Protocol as the public-facing interface — [medium – Python Interfaces: ABC, Protocol, or Both](https://tconsta.medium.com/python-interfaces-abc-protocol-or-both-3c5871ea6642)
- A data-engineering team adopted ABCs after a bug caused by inconsistent implementations of a shared `preprocess()` method across loaders — [dev.to – Python Fundamentals: ABC](https://dev.to/devopsfundamentals/python-fundamentals-abc-4fd)
- confluent-kafka-python exposes both `poll()` (per-message) and `consume(num_messages, timeout)` (batch), so a streaming adapter can offer both a per-event `__next__` and a batch `consume(n)` path — search result general knowledge confirmed in query on Kafka Python consumer patterns
- The Protean framework's in-memory adapter fully implements the port interface and acts as both a reference implementation and a default for testing — [docs.proteanhq.com – Ports & Adapters](https://docs.proteanhq.com/concepts/ports-and-adapters/)

### Inferences
- The minimal viable interface is: `load() -> list[dict]` (batch pull), `stream() -> Iterator[dict]` (lazy pull), and optionally `close()` for resource cleanup. Async variants (`aload`, `astream`) should be added only when the engine is async-native, not by default.
- A `typing.Protocol` definition is the best starting point because it imposes zero inheritance tax on adapters wrapping third-party libraries (SQLAlchemy session, Kafka consumer, pyarrow Table).
- An in-memory adapter should be built alongside the Protocol definition so tests never require external infrastructure.

### Gaps
- No publicly available benchmark comparing per-event vs. batch adapter invocation overhead specifically in a Python rules engine loop.
- No canonical open-source Python rules engine (experta, py-rules-engine, Vulcan) has documented a FactSource adapter interface; this appears to be a design that each project implements ad hoc.

---

## Field-Name Normalization Across Sources

### Takeaway
No Python data library performs cross-source field name normalization automatically; each source returns its native names (SQL column names, Avro field names, JSON keys, Parquet column names), so normalization must be handled at the adapter boundary with an explicit mapping step.

### Cited Findings
- SQLAlchemy 1.4+ rows expose `row._mapping` (a read-only dict-like view) or `dict(row._mapping)` for `select()`-style results; column names come from the SQL schema exactly as defined — [slingacademy.com – SQLAlchemy Convert Query Results to Dictionary](https://www.slingacademy.com/article/sqlalchemy-convert-query-results-into-dictionary/)
- A column-iteration comprehension pattern `{col.name: getattr(row, col.name) for col in Model.__table__.columns}` is widely used for ORM models and preserves SQL column names unchanged — [slingacademy.com](https://www.slingacademy.com/article/sqlalchemy-convert-query-results-into-dictionary/)
- PyArrow's `Table.to_pydict()` returns columns under their stored names; `rename_columns()` is a separate method that returns a new table with supplied names — [arrow.apache.org – PyArrow Table API](https://arrow.apache.org/docs/python/generated/pyarrow.Table.html)
- PyArrow's `from_pydict` infers column names from dict keys and `from_pandas` can map string columns to `large_string`, producing different Arrow types from the same logical data depending on entry point — [arrow.apache.org](https://arrow.apache.org/docs/python/generated/pyarrow.Table.html)
- Avro field resolution matches reader and writer schemas by field name; a field present only in the writer is ignored, and a field present only in the reader takes its declared default — [martin.kleppmann.com – Schema Evolution in Avro, Protocol Buffers and Thrift](https://martin.kleppmann.com/2012/12/05/schema-evolution-in-avro-protocol-buffers-thrift.html)
- Avro renames without aliases break field resolution; the reader must declare an alias matching the old name to migrate gracefully — [oneuptime.com – Schema Evolution Issues](https://oneuptime.com/blog/post/2026-01-24-schema-evolution-issues/markdown)
- The dlt (data load tool) library applies its own normalization layer on top of PyArrow, producing a mapping from original field names to normalized names and a reverse mapping — [dlthub.com – PyArrow helper API](https://dlthub.com/docs/api_reference/dlt/common/libs/pyarrow)

### Inferences
- The safest design places a `field_map: dict[str, str]` parameter on each adapter that maps source-native names to canonical fact field names. This keeps normalization explicit and auditable.
- A snake_case normalization utility (e.g., lowercase, replace spaces and hyphens with underscores) covers most REST API and SQL naming divergences without a hand-authored map.
- For Parquet and Avro, the schema already carries authoritative field names; adapters should read the schema at initialization time and apply any renaming once, not on each record.
- Namespace-qualified Avro names (e.g., `com.example.UserCreated.user_id`) need a stripping strategy agreed at project setup; a simple `name.split(".")[-1]` works for most cases but collides if two namespaces share a short name.

### Gaps
- No source confirmed how fastavro's `parse_schema` handles field name normalization or aliases at deserialization time; the fastavro documentation or source should be checked directly.
- No authoritative Python style guide defines a canonical "fact field naming convention" that rules engines should target.

---

## In-Memory Fact Representation

### Takeaway
Frozen dataclasses (as used by the Vulcan engine) offer the best balance of immutability, IDE tooling, and runtime performance for a typed fact model; plain `dict` is the right choice when source schemas are fully dynamic or unknown at development time.

### Cited Findings
- Vulcan's `Fact` base class applies `@dataclass(frozen=True, kw_only=True)` via a metaclass, making all fact instances immutable after creation and requiring keyword arguments — [latchfield.com – Understanding Facts](https://latchfield.com/vulcan/docs/guides/understanding-facts/)
- Vulcan's working memory accepts only `Fact` objects, not plain dicts; the `|` operator produces a new `Fact` instance from a partial merge, and dict-style key access (`fact['field']`) is also supported — [latchfield.com](https://latchfield.com/vulcan/docs/guides/understanding-facts/)
- `TypedDict` provides only a static type annotation with no runtime enforcement or defaults, making it unsuitable as the primary runtime representation for facts — search result inference from [pypi.org – modict](https://pypi.org/project/modict/)
- Pydantic models validate input at instantiation and are the backbone of FastAPI's request parsing; they add measurable overhead compared with plain dataclasses, which do not validate — [pydantic.dev](https://pydantic.dev/docs/validation/v2.3/api-reference/dataclasses)
- The typedlogic project lets predicates be defined as Pydantic, dataclass, or SQLModel classes, showing that the Python rules-engine community has not settled on a single representation — [pypi.org – typedlogic](https://pypi.org/project/typedlogic/0.1.2)
- PyArrow `RecordBatch` is efficient for columnar batch evaluation (SIMD operations, zero-copy slicing) but requires the rules engine to operate in a vectorized, columnar style rather than per-record — from PyArrow architecture knowledge; no web source specifically confirms this for rules engines

### Inferences
- For a rules engine that evaluates rules record-by-record, `dict` is the universal lowest-common-denominator that all adapters can produce and all rule conditions can consume via key access.
- Typed frozen dataclasses add value when the schema is known at development time and the team wants IDE autocompletion and early error detection; the conversion overhead from dict (via `MyFact(**row_dict)`) is negligible for most workloads.
- Pydantic models are worth the overhead only when incoming facts require validation (e.g., API ingestion paths), not for internal database or file sources where the schema is already trusted.
- A hybrid: adapters always produce `dict`, and an optional `FactFactory` layer converts dicts to typed dataclasses at the engine boundary. This keeps adapter code simple and typing optional.
- `RecordBatch` / Arrow tables belong at a separate "batch evaluation" interface, not the core fact representation, because they require a fundamentally different rule-evaluation strategy.

### Gaps
- No benchmark comparing `dict` vs. frozen dataclass vs. Pydantic model for fact instantiation throughput in a Python rules engine loop at >10k facts/sec.

---

## Streaming Sources: Per-Event vs. Micro-Batch

### Takeaway
Per-event processing minimizes end-to-end latency (sub-100ms achievable) but pays higher Python-side CPU overhead per message; micro-batching via `consume(n)` reduces overhead but adds batch-assembly latency and complicates offset commit and error handling.

### Cited Findings
- confluent-kafka-python's `poll()` returns one message per call and its `consume(num_messages, timeout)` returns a list, enabling both styles from the same client — from confluent-kafka-python documentation (general knowledge; no single web source confirmed this in search results)
- A Kafka Summit talk reported a 65% cost reduction by moving a multi-petabyte stream from per-event to batch (Spark+Airflow), with trade-offs in wait time, reprocessing, and outage recovery — [kafka-summit.org – Should You Read Kafka as a Stream or in Batch?](https://www.kafka-summit.org/sessions/should-you-read-kafka-as-a-stream-or-in-batch-should-you-even-care)
- A PyData London 2026 talk proposes treating Kafka as a source of Arrow-backed DataFrames (micro-batches), noting there are trade-offs that users should be aware of but not detailing them in the abstract — [pretalx.com – PyData London 2026](https://pretalx.com/pydata-london-2026/talk/BPJEKV/)
- Snuba (Sentry's Python Kafka consumer) notes that if per-event work exceeds `max.poll.interval.ms`, the consumer is declared dead and a rebalance is triggered — [baseplate.readthedocs.io – Kafka consumer source](https://baseplate.readthedocs.io/en/latest/_modules/baseplate/frameworks/queue_consumer/kafka.html)
- Baseplate's Kafka consumer records per-message processing time as a histogram and lets exceptions crash the consumer to avoid committing offsets for unprocessed messages — [baseplate.readthedocs.io](https://baseplate.readthedocs.io/en/latest/_modules/baseplate/frameworks/queue_consumer/kafka.html)
- KafPy (a Rust-core Python Kafka library) supports batch handlers and dead-letter queue, but does not allow async handlers — [pypi.org – kafpy](https://pypi.org/project/kafpy/)

### Inferences
- A FactSource adapter wrapping Kafka should expose both a `stream() -> Iterator[dict]` (per-event, delegates to `poll()`) and a `consume_batch(n: int) -> list[dict]` method. The rules engine picks its consumption style.
- Per-event is correct when rules must fire within the message's processing window and the per-rule evaluation is fast (<1ms). Micro-batching is correct when rules operate over aggregates or when columnar evaluation (PyArrow) is used.
- Offset management belongs in the adapter, not the rules engine. The adapter should commit only after the engine returns control, and expose a `nack()` or dead-letter path for rule-evaluation failures.
- Kinesis adapters follow the same pattern (per-record vs. per-shard-batch) but commit via sequence number checkpointing rather than Kafka offset commits; the adapter interface should abstract this away.

### Gaps
- No Python-specific latency benchmark for a rules engine (e.g., experta, Vulcan) consuming per-event Kafka messages vs. micro-batches.
- No confirmed source on whether Kinesis Enhanced Fan-Out changes the per-event vs. micro-batch trade-off for Python consumers.

---

## Fact Context: What a Fact Must Carry Beyond Raw Data

### Takeaway
A fact context envelope should carry at minimum: `source_id` (which adapter produced it), `ingested_at` (UTC timestamp), `schema_version` (for Avro/Parquet sources), and a `trace_id` (for lineage and debugging); everything else should be opt-in.

### Cited Findings
- One ML lineage guide proposes a Python dataclass for a lineage node with fields: `node_id`, `node_type`, `version`, `timestamp`, `inputs: list[str]`, and `metadata: dict` — [reintech.io – Implement Data Lineage Tracking in ML Pipelines](https://reintech.io/blog/implement-data-lineage-tracking-ml-pipelines)
- A dataset node in the same guide adds a `schema_hash` field to detect schema drift — [reintech.io](https://reintech.io/blog/implement-data-lineage-tracking-ml-pipelines)
- A case study on Kafka-sourced data describes a dashboard discrepancy traced to schema drift in a source Kafka topic that spread through downstream jobs; lineage tracking is argued as a debugging tool, not just compliance — [dev.to – Data Lineage with Python](https://dev.to/devopsfundamentals/big-data-fundamentals-data-lineage-with-python-feo)
- A 2025 academic paper on schema lineage describes "semantic drift" where transformations cause original metadata to stop matching downstream data; it proposes tracking source schemas, source tables, transformation logic, and aggregations — [arxiv.org – Schema Lineage Extraction at Scale](https://arxiv.org/html/2508.07179v1)
- OVHcloud's platform records lineage automatically for built-in actions; for custom Python actions, lineage is opt-in and the developer declares inputs and outputs explicitly — [docs.ovhcloud.com – Python SDK Lineage](https://docs.ovhcloud.com/en/guides/public-cloud/data-platform/developers-python-sdk-lineage.md)

### Inferences
- The minimal context envelope is a separate dataclass (not embedded in the fact data dict) to keep rule conditions clean: `FactContext(source_id: str, ingested_at: datetime, schema_version: str | None, trace_id: str)`.
- A `raw` field holding the original, un-normalized record is valuable for debugging schema drift but should be off by default due to memory cost.
- For streaming sources, the context should also carry partition/offset (Kafka) or sequence number (Kinesis) to enable replay and deduplication.
- Schema version should be a string (e.g., Avro's schema fingerprint or Confluent Schema Registry subject+version) rather than an integer, because different source types have different versioning schemes.

### Gaps
- No Python rules engine project was found that documents a standard fact context envelope; this appears to be an unsolved problem in the Python ecosystem.

---

## Minimum Viable Adapter: Callable vs. Full Protocol

### Takeaway
A `Callable[[], dict]` plus a `register_source(name, fn)` function is sufficient for 80% of batch use cases with a single rules engine; it becomes insufficient when sources need connection lifecycle management, streaming, or context metadata.

### Cited Findings
- A decorator-based registry (`register(key)` stores any callable under a string key, `create(name)` looks it up and calls it) is a documented pattern in Python — [pattern-kit.readthedocs.io – Factory Module](https://pattern-kit.readthedocs.io/en/latest/_modules/pattern_kit/creational/factory.html)
- `dynamic-factory`'s `FuncFactory` accepts functions (not just classes) with a decorator and optional alias and group arguments — [pypi.org – dynamic-factory](https://pypi.org/project/dynamic-factory/0.1.9/)
- MolSSI's factory pattern guide notes a factory acts as a single entry point that hides which concrete adapter gets built — [education.molssi.org – Factory Design Pattern](https://education.molssi.org/oop_and_design_patterns/09-Factory.html)
- Protean's adapter registry uses Python entry points (`protean.providers` group) for discovery, so third-party adapters become available after installation without source changes — [docs.proteanhq.com](https://docs.proteanhq.com/concepts/ports-and-adapters/)
- Protean declares adapter capabilities as flags; capability-gated methods raise `NotSupportedError` when unsupported, and the conformance test suite runs only tests for declared capabilities — [docs.proteanhq.com](https://docs.proteanhq.com/concepts/ports-and-adapters/)

### Inferences
- Start with `register_source(name: str, fn: Callable[[], dict | list[dict]])`. This covers: SQL queries wrapped in a lambda, REST API calls, file readers. It has zero abstraction overhead.
- Upgrade to a Protocol when any of these are needed: (a) streaming (need `stream()` or `__iter__`), (b) lifecycle management (need `open()` / `close()`), (c) context metadata (need `load_with_context() -> tuple[dict, FactContext]`), (d) async support.
- Capability flags (as in Protean) are worth adding before the Protocol grows large; they let the engine query whether an adapter supports streaming without trying to call `stream()` and catching `AttributeError`.
- Entry-point discovery is premature for an internal project; explicit `register_source` calls at application startup are simpler and more readable.

### Gaps
- No source compared the actual maintenance cost of a `Callable`-based registry vs. a Protocol-based adapter system over a multi-year project lifecycle.

---

## Risks of Early Abstraction

### Takeaway
Introducing a multi-source FactSource abstraction before at least two real source types are needed creates API churn, hidden complexity, and a maintenance burden that grows faster than the value it delivers.

### Cited Findings
- A developer who built a "flexible" data layer for many backends ended up with one backend in use, a config object with twelve special cases, and an abstraction wrapping a single fetch call — [nitesh.is-a.dev – Useless Abstractions](https://nitesh.is-a.dev/posts/useless-abstractions)
- The rule-of-three: wait for two or more real implementations before adding an interface; avoid abstract base classes before a second subclass exists — [dev.to – The Abstraction Tax](https://dev.to/utak3r/the-abstraction-tax-55mn)
- An interface with only one real implementation forces readers to pay for indirection nobody needs; the advice is to ask "can you name the second consumer?" before adding the interface — [codingshuttle.com – Common Software Design Mistakes](https://www.codingshuttle.com/low-level-system-design-lld-handbook/common-software-design-mistakes)
- A PyCon AU 2024 talk post-mortem describes a sophisticated Django multi-tenancy library that was never used in production because it was over-engineered — [pycon.org.au – PyCon AU 2024](https://2024.pycon.org.au/program/M3KJ3V)
- YAGNI and KISS: "write the direct version first, duplicate it for a second source, and abstract only at the third" — cited from multiple sources including [archman.dev – Over-Abstracting: Too Many Layers](https://archman.dev/docs/anti-patterns-and-pitfalls/over-abstracting-too-many-layers)
- A Better Programming piece reports a team substantially cutting feature file counts after removing premature abstractions — [betterprogramming.pub – Avoiding Premature Software Abstractions](https://betterprogramming.pub/avoiding-premature-software-abstractions-8ba2e990930a) (note: this URL returned 403; the claim comes from the search snippet, not a full page read)

### Inferences
- The right trigger for building the FactSource abstraction in fluxrules is: two or more source types are actively used in production or in a real integration test. One SQL source and one REST source, both in use, justifies it. One SQL source alone does not.
- API churn risk is highest during the first three months of a new abstraction. Lock down the `load()` and `stream()` signatures before advertising them as stable.
- Field-name normalization is the most likely source of API churn; defer it to a separate `FieldMapper` utility rather than baking it into the `FactSource` interface itself.
- A `Callable`-based `register_source` is the right starting point precisely because it is easy to delete. A Protocol with four methods and a capability flag system is hard to remove once tests depend on it.
- Introducing the abstraction in a `fluxrules.contrib.sources` namespace (opt-in) rather than in the core keeps the core engine clean and signals that the abstraction is experimental.

### Gaps
- No source quantified the engineering cost (in hours) of refactoring from a direct data-access pattern to a FactSource abstraction vs. building the abstraction upfront.
- The specific fluxrules codebase was not analyzed for whether it already has any implicit data-loading patterns that would constrain the adapter interface.
