"""Runtime helpers for FluxRules engines.

Exposes:
- :func:`evaluate_batch_parallel` - process-based batch evaluation for
  multi-core throughput. See :mod:`.worker_pool`.
- :class:`AsyncActionDispatcher` / :class:`ThreadedActionDispatcher` - decouple
  CPU-bound evaluation from I/O-bound action firing. See
  :mod:`.action_dispatcher`.
- :class:`DedupEvaluator` and backends - memoize ``evaluate`` on repeated
  facts. See :mod:`.dedup_cache`.
"""

from fluxrules.engine.runtime.action_dispatcher import (
    Activation,
    AsyncActionDispatcher,
    DispatchStats,
    ThreadedActionDispatcher,
    activations_from_result,
)
from fluxrules.engine.runtime.dedup_cache import (
    DedupEvaluator,
    DedupStats,
    LRUDedupBackend,
    RedisDedupBackend,
    canonical_fact_key,
)
from fluxrules.engine.runtime.worker_pool import evaluate_batch_parallel

__all__ = [
    # Async action firing
    "Activation",
    "AsyncActionDispatcher",
    # Fact deduplication
    "DedupEvaluator",
    "DedupStats",
    "DispatchStats",
    "LRUDedupBackend",
    "RedisDedupBackend",
    "ThreadedActionDispatcher",
    "activations_from_result",
    "canonical_fact_key",
    "evaluate_batch_parallel",
]
