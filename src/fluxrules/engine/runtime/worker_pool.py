"""Process-based worker pool for CPU-bound fact evaluation.

Python's GIL prevents threads from parallelizing CPU-bound condition
evaluation. ``PhreakEngine._evaluate_parallel`` uses threads (useful for the
caching/dedup it provides, but not for multi-core speedup). To actually use
multiple cores for high-throughput batch processing, this module shards a batch
of facts across *processes*, each running its own engine instance.

Correctness guarantee: each fact is evaluated by a normal engine instance using
the public ``evaluate`` API, so the result for any fact is identical to
single-process evaluation. Only the *distribution* of work changes, never the
result.

Most callers should use :meth:`BaseEngine.evaluate_batch
<fluxrules.engine.base.BaseEngine.evaluate_batch>`, which rebuilds the calling
engine (with every option it was created with) in each worker and returns full
:class:`~fluxrules.domain.models.EvaluationResult` objects::

    results = engine.evaluate_batch(facts, workers=4)

:func:`evaluate_batch_parallel` is the older, lower-level helper. It builds a
default engine from ``rules`` and returns only fired rule ids::

    from fluxrules.engine.runtime import evaluate_batch_parallel

    results = evaluate_batch_parallel(
        rules=rules,           # list[Rule]
        facts=facts,           # list[dict]
        num_workers=4,
        streaming_mode=False,  # streaming is per-process stateful; see note
    )
    # results[i] is the list of fired rule ids for facts[i]

Note on streaming mode: streaming relies on per-engine dirty-tracking state.
Sharding facts across processes splits that state, so streaming is only
meaningful when an ordered fact stream stays on one worker. For batch parallel
throughput use ``streaming_mode=False`` (stateless), which is the mode whose
results are independent of ordering and therefore safe to shard.
"""

from __future__ import annotations

import os
import pickle  # nosec B403 - only loads bytes this module produced
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

# Module-level worker state (one engine per process, built once).
_WORKER_ENGINE: Any = None


@dataclass
class BatchOutcome:
    """What a sharded batch produced, merged back into input order.

    Attributes:
        results: One entry per fact: an ``EvaluationResult``, or a list of
            fired rule ids when ids only were requested. Facts after ``error``
            may be missing.
        quarantined: ``QuarantinedFact`` entries from the workers, in input
            order, for facts before ``error`` (a loop would stop there).
        error: The exception raised for the lowest-index failing fact, or
            ``None``.
        comparison_issues: Every comparison the workers could not make, once
            each, for facts before ``error``. Worker processes do not emit
            ``ComparisonWarning``; :func:`warn_comparison_issues` repeats it in
            the parent, once per issue, as a single process would.
    """

    results: list[Any] = field(default_factory=list)
    quarantined: list[Any] = field(default_factory=list)
    error: BaseException | None = None
    comparison_issues: list[Any] = field(default_factory=list)


def _init_worker(engine_class: type, settings: dict[str, Any], rules: list[Any]) -> None:
    """Build the single engine this process evaluates with."""
    global _WORKER_ENGINE
    _WORKER_ENGINE = engine_class(**settings)
    _WORKER_ENGINE.load_rules(rules)


def _init_worker_from_payload(payload: bytes) -> None:
    """Process initializer: unpickle ``(engine_class, settings, rules)`` and build the engine.

    The parent pickles the payload once (see :func:`build_payload`), so it is
    not serialized again for every worker.
    """
    # Bytes from build_payload in the parent process, never outside input.
    engine_class, settings, rules = pickle.loads(payload)  # noqa: S301  # nosec B301
    _init_worker(engine_class, settings, rules)


def _eval_chunk(
    task: tuple[int, list[Any], bool, bool],
) -> tuple[
    list[Any], list[tuple[int, Any]], tuple[int, BaseException] | None, list[tuple[int, Any]]
]:
    """Evaluate one chunk with this process's engine.

    ``task`` is ``(start, facts, ids_only, in_worker)``, where ``start`` is the
    chunk's offset in the whole batch, so the indexes returned are global. The
    chunk stops at the first exception, as a loop over ``evaluate`` would. In a
    worker process an exception that cannot be pickled is replaced by a
    ``RuntimeError`` describing it; in this process the original is kept.

    The comparison issues of each fact come back with its index. A worker
    process does not emit ``ComparisonWarning`` itself: the parent repeats it
    (see :func:`warn_comparison_issues`), so it is shown once, where the
    caller can see and filter it.
    """
    from fluxrules.domain.errors import ComparisonWarning

    start, facts, ids_only, in_worker = task
    engine = _WORKER_ENGINE
    intake = getattr(engine, "_fact_intake", None)
    results: list[Any] = []
    quarantined: list[tuple[int, Any]] = []
    issues: list[tuple[int, Any]] = []
    error: tuple[int, BaseException] | None = None
    with warnings.catch_warnings():
        if in_worker:
            warnings.simplefilter("ignore", ComparisonWarning)
        for offset, fact in enumerate(facts):
            index = start + offset
            if intake is not None:
                # Each entry is returned once; the parent keeps the record.
                intake.quarantine.clear()
            try:
                result = engine.evaluate(fact)
            except Exception as exc:  # noqa: BLE001 - re-raised in the parent
                error = (index, _picklable(exc) if in_worker else exc)
                break
            if intake is not None and intake.quarantine:
                quarantined.append((index, intake.quarantine[-1]))
            issues.extend((index, issue) for issue in result.comparison_issues)
            results.append(list(result.fired_rules) if ids_only else result)
    return results, quarantined, error, issues


def _picklable(exc: BaseException) -> BaseException:
    """Return ``exc`` if it survives pickling, else a RuntimeError describing it."""
    try:
        # Round-trips an exception this process is holding, never outside input.
        pickle.loads(pickle.dumps(exc))  # noqa: S301  # nosec B301
    except Exception:  # noqa: BLE001 - any pickling failure
        return RuntimeError(f"{type(exc).__name__}: {exc}")
    return exc


def _chunk(seq: list, n_chunks: int) -> list[tuple[int, list]]:
    """Split ``seq`` into ``n_chunks`` roughly equal contiguous chunks with offsets."""
    if n_chunks <= 1 or len(seq) <= 1:
        return [(0, seq)]
    size = max(1, (len(seq) + n_chunks - 1) // n_chunks)
    return [(i, seq[i : i + size]) for i in range(0, len(seq), size)]


def build_payload(engine_class: type, settings: dict[str, Any], rules: list[Any]) -> bytes:
    """Pickle what the workers need, once, or raise a clear ``ValueError``.

    Worker processes receive the engine class, its settings and the rules by
    pickling, so a lambda in a ``fact_pipeline`` or a class defined inside a
    function would otherwise fail deep inside the pool with a confusing
    traceback. On failure each part is tried alone so the message can name it.
    """
    try:
        return pickle.dumps((engine_class, settings, rules))
    except Exception:  # noqa: BLE001, S110 - any pickling failure; named below
        pass
    parts: list[tuple[str, Any]] = [
        ("the engine class", engine_class),
        *settings.items(),
        ("rules", rules),
    ]
    for name, value in parts:
        try:
            pickle.dumps(value)
        except Exception as exc:  # noqa: BLE001 - any pickling failure
            raise ValueError(
                f"evaluate_batch with workers > 1 needs picklable engine settings: "
                f"{name} could not be pickled ({type(exc).__name__}: {exc}). Lambda "
                "functions and classes defined inside a function cannot be sent to "
                "worker processes. Use workers=1, or a named module-level function or class."
            ) from None
    raise ValueError("evaluate_batch with workers > 1: the engine settings could not be pickled")


def run_sharded(
    engine_class: type,
    settings: dict[str, Any],
    rules: list[Any],
    facts: list[Any],
    workers: int,
    *,
    ids_only: bool = False,
    payload: bytes | None = None,
) -> BatchOutcome:
    """Evaluate ``facts`` with engines rebuilt from ``settings`` in ``workers`` processes.

    ``workers`` is capped to ``len(facts)``. With one worker no process pool is
    started and nothing is pickled: the engine is built in this process.
    ``payload`` is the output of :func:`build_payload`, when the caller has it.
    """
    if not facts:
        return BatchOutcome()
    workers = max(1, min(workers, len(facts)))

    if workers == 1:
        # Avoid process overhead entirely (also keeps this usable in
        # environments where spawning processes is restricted).
        _init_worker(engine_class, settings, rules)
        try:
            chunk_outputs = [_eval_chunk((0, facts, ids_only, False))]
        finally:
            # Reset module state so repeated in-process calls stay clean.
            globals()["_WORKER_ENGINE"] = None
    else:
        if payload is None:
            payload = pickle.dumps((engine_class, settings, rules))
        tasks = [(start, chunk, ids_only, True) for start, chunk in _chunk(facts, workers)]
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker_from_payload,
            initargs=(payload,),
        ) as executor:
            # executor.map preserves input order, so concatenating chunk
            # results reproduces the original fact order exactly.
            chunk_outputs = list(executor.map(_eval_chunk, tasks))

    outcome = BatchOutcome()
    errors = [error for _, _, error, _ in chunk_outputs if error is not None]
    first_error = min(errors, key=lambda pair: pair[0]) if errors else None
    stop = first_error[0] if first_error is not None else len(facts)
    seen: set[Any] = set()
    for results, quarantined, _, issues in chunk_outputs:
        outcome.results.extend(results)
        outcome.quarantined.extend(entry for index, entry in quarantined if index < stop)
        for index, issue in issues:
            if index < stop and issue not in seen:
                seen.add(issue)
                outcome.comparison_issues.append(issue)
    if first_error is not None:
        outcome.results = outcome.results[:stop]
        outcome.error = first_error[1]
    return outcome


def warn_comparison_issues(issues: list[Any], mode: str | None) -> None:
    """Emit, in this process, the ``ComparisonWarning`` workers did not.

    Only under the default ``uncomparable=None``, once per issue per process,
    as :func:`fluxrules.engine.uncomparable.report` does.
    """
    if mode is not None:
        return
    from fluxrules.engine.uncomparable import warn_once

    for issue in issues:
        warn_once(issue)


def evaluate_batch_parallel(
    rules: list[Any],
    facts: list[dict],
    num_workers: int | None = None,
    streaming_mode: bool = False,
) -> list[list[int]]:
    """Evaluate ``facts`` across ``num_workers`` processes.

    Each worker builds a default ``PhreakEngine`` (only ``streaming_mode`` is
    passed). To keep every option of an engine you configured, use
    ``engine.evaluate_batch(facts, workers=N)`` instead.

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
    from fluxrules.engine.phreak import PhreakEngine

    workers = num_workers or os.cpu_count() or 1
    outcome = run_sharded(
        PhreakEngine,
        {"streaming_mode": streaming_mode},
        rules,
        facts,
        workers,
        ids_only=True,
    )
    from fluxrules.engine.configuration import get_config

    warn_comparison_issues(outcome.comparison_issues, get_config().uncomparable)
    if outcome.error is not None:
        raise outcome.error
    return outcome.results


__all__ = [
    "BatchOutcome",
    "build_payload",
    "evaluate_batch_parallel",
    "run_sharded",
    "warn_comparison_issues",
]
