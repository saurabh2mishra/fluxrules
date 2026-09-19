"""Process-based worker pool for CPU-bound fact evaluation.

Python's GIL prevents threads from parallelizing CPU-bound condition
evaluation. ``PhreakEngine._evaluate_parallel`` uses threads (useful for the
caching/dedup it provides, but not for multi-core speedup). To actually use
multiple cores for high-throughput batch processing, this module shards a batch
of facts across *processes*, each running its own engine instance.

Correctness guarantee: each fact is evaluated by a normal engine instance using
the public ``evaluate`` API, so the fired-rule set for any fact is identical to
single-process evaluation. Only the *distribution* of work changes, never the
result.

Usage::

    from fluxrules.engine.runtime import evaluate_batch_parallel

    results = evaluate_batch_parallel(
        rules=rules,           # list[Rule]
        facts=facts,           # list[dict]
        num_workers=4,
        streaming_mode=False,  # streaming is per-process stateful; see note
    )
    # results[i] is the set of fired rule ids for facts[i]

Note on streaming mode: streaming relies on per-engine dirty-tracking state.
Sharding facts across processes splits that state, so streaming is only
meaningful when an ordered fact stream stays on one worker. For batch parallel
throughput use ``streaming_mode=False`` (stateless), which is the mode whose
results are independent of ordering and therefore safe to shard.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any

# Module-level worker state (one engine per process, built once).
_WORKER_ENGINE: Any = None


def _init_worker(rules: list[Any], streaming_mode: bool) -> None:
    """Process initializer: build a single engine per worker process."""
    global _WORKER_ENGINE
    # Imported lazily inside the worker so the parent process does not need to
    # pickle the engine class graph.
    from fluxrules.engine.phreak import PhreakEngine

    _WORKER_ENGINE = PhreakEngine(streaming_mode=streaming_mode)
    _WORKER_ENGINE.load_rules(rules)


def _eval_chunk(facts_chunk: list[dict]) -> list[list[int]]:
    """Evaluate a chunk of facts in the worker, returning fired-rule id lists."""
    engine = _WORKER_ENGINE
    out: list[list[int]] = []
    for fact in facts_chunk:
        out.append(list(engine.evaluate(fact).fired_rules))
    return out


def _chunk(seq: list, n_chunks: int) -> list[list]:
    """Split ``seq`` into ``n_chunks`` roughly equal contiguous chunks."""
    if n_chunks <= 1 or len(seq) <= 1:
        return [seq]
    size = max(1, (len(seq) + n_chunks - 1) // n_chunks)
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def evaluate_batch_parallel(
    rules: list[Any],
    facts: list[dict],
    num_workers: int | None = None,
    streaming_mode: bool = False,
) -> list[list[int]]:
    """Evaluate ``facts`` across ``num_workers`` processes.

    Args:
        rules: Rules to load into each worker engine.
        facts: Facts to evaluate. Order is preserved in the output.
        num_workers: Number of worker processes (default: ``os.cpu_count()``).
        streaming_mode: Engine streaming mode. Use ``False`` for batch parallel
            throughput (see module note about streaming + sharding).

    Returns:
        A list parallel to ``facts``; each element is the list of fired rule
        ids for the corresponding fact (identical to single-process results).
    """
    if not facts:
        return []

    workers = num_workers or os.cpu_count() or 1
    workers = max(1, min(workers, len(facts)))

    # Single worker: avoid process overhead entirely (also keeps this usable in
    # environments where spawning processes is restricted).
    if workers == 1:
        _init_worker(rules, streaming_mode)
        try:
            return _eval_chunk(facts)
        finally:
            # Reset module state so repeated in-process calls stay clean.
            globals()["_WORKER_ENGINE"] = None

    chunks = _chunk(facts, workers)
    results: list[list[int]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(rules, streaming_mode),
    ) as executor:
        # executor.map preserves input order, so concatenating chunk results
        # reproduces the original fact order exactly.
        for chunk_result in executor.map(_eval_chunk, chunks):
            results.extend(chunk_result)
    return results


__all__ = ["evaluate_batch_parallel"]
