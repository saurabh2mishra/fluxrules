"""Pure-Python config for core engine - no pydantic-settings needed."""

from dataclasses import dataclass


@dataclass
class EngineConfig:
    """Pure-Python config for core engine - no pydantic-settings needed."""

    strict_null_handling: bool = False
    strict_type_comparison: bool = False
    boolean_string_coercion: bool = False
    validation_strict_bool_numeric: bool = False
    use_optimized_engine: bool = True
    rule_engine_type: str = "PHREAK"
    session_max_facts: int = 1000
    session_ttl_seconds: int = 3600
    session_max_concurrent: int = 100

    # Tuple memory management (used by DB-backed engines)
    tuple_ttl_seconds: int = 300
    tuple_cleanup_interval_seconds: int = 60
    rule_memory_quota_mb: float = 100.0
    rule_quota_enforcement: str = "warn"  # "warn", "reject", or "evict"

    # Memory bounding (PHREAK P2.3).
    # node_memory_max_entries: hard cap on the streaming NodeMemory LRU cache
    #   (true LRU eviction beyond this; see infrastructure/node_memory.py).
    # working_memory_high_water_mark: number of resident facts above which the
    #   working memory logs a one-time WARNING. A pure stateless scoring path
    #   keeps working memory near-empty; a climbing fact count signals an
    #   assert-without-retract leak (§6) that would otherwise grow for the full
    #   TTL window before becoming visible. 0 disables the watchdog.
    node_memory_max_entries: int = 100_000
    working_memory_high_water_mark: int = 100_000

    # Parallel rule evaluation
    # Default to the sequential path (threshold effectively
    # disabled). Condition evaluation is pure-Python and GIL-bound, so the
    # ThreadPoolExecutor cannot run it concurrently - profiling showed the
    # thread machinery (submit / lock acquire / RLock / futures) accounted for
    # ~half of total runtime, making the parallel path ~2.2x SLOWER than
    # sequential on identical work. The pool is kept opt-in (lower this
    # threshold) only for workloads dominated by I/O-bound custom actions; for
    # true multi-core scaling use the process-based
    # fluxrules.engine.runtime.evaluate_batch_parallel helper instead.
    parallel_threshold: int = 1_000_000_000  # Effectively sequential by default
    parallel_workers: int = 4  # Thread pool size for parallel evaluation (opt-in)


# Module-level default (can be replaced by API layer)
_default_config = EngineConfig()


def get_config() -> EngineConfig:
    return _default_config


def set_config(config: EngineConfig) -> None:
    global _default_config
    _default_config = config
