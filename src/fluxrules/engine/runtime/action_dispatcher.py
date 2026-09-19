"""Async action dispatch.

The engine's hot path is CPU-bound: it decides *which* rules fire. But the
*actions* those rules trigger (send an alert, write a row, call a webhook) are
frequently **I/O-bound**. Running them inline in ``evaluate`` puts I/O latency on
the throughput critical path - a slow webhook stalls the next fact.

This module decouples the two stages:

    evaluate(fact) -> activations  ──(queue)──►  ActionDispatcher fires actions
       (CPU-bound, fast)                            (I/O-bound, concurrent)

The evaluation thread/process only *enqueues* the fired action names plus their
fact context; a pool of async workers drains the queue and executes the actions
against the :class:`~fluxrules.plugins.actions.ActionRegistry` concurrently. The
engine never blocks on action I/O.

Soundness
---------
Dispatch does **not** change which rules fire - it only changes *when and on
what thread* their actions run. The set of dispatched ``(rule, action)`` pairs
is exactly the engine's ``fired_rules``/``actions`` for each fact. Action
*ordering* across facts is not guaranteed (that is the point of concurrency); if
an action requires ordering it should not be dispatched asynchronously.

Two entry points:

- :class:`AsyncActionDispatcher` - asyncio-native; use inside an event loop.
- :class:`ThreadedActionDispatcher` - runs its own event loop on a background
  thread so synchronous evaluation code can ``dispatch(...)`` and keep going.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from fluxrules.plugins.actions import ActionRegistry
from fluxrules.plugins.actions import action_registry as _global_registry

logger = logging.getLogger(__name__)


@dataclass
class Activation:
    """A single action to fire, with the fact context that triggered it.

    ``action`` is an action name registered in the :class:`ActionRegistry`.
    ``params`` are the keyword arguments passed to the action handler; by
    default the triggering fact is forwarded under ``facts``.
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    rule_id: int | None = None


@dataclass
class DispatchStats:
    """Counters tracking dispatched / succeeded / failed actions."""

    dispatched: int = 0
    succeeded: int = 0
    failed: int = 0

    @property
    def pending(self) -> int:
        return self.dispatched - self.succeeded - self.failed


def activations_from_result(
    result: Any,
    facts: dict[str, Any] | None = None,
) -> list[Activation]:
    """Build :class:`Activation` objects from an ``EvaluationResult``.

    Pairs each fired rule id with its action (when both are available) and
    attaches the triggering ``facts`` as the action's ``facts`` parameter.
    Falls back to the result's ``actions`` list when rule/action pairing is not
    one-to-one.
    """
    activations: list[Activation] = []
    fired = list(getattr(result, "fired_rules", []) or [])
    actions = list(getattr(result, "actions", []) or [])
    base_params = {"facts": facts} if facts is not None else {}

    if fired and len(fired) == len(actions):
        for rid, action in zip(fired, actions):
            if action:
                activations.append(Activation(action=action, params=dict(base_params), rule_id=rid))
    else:
        for action in actions:
            if action:
                activations.append(Activation(action=action, params=dict(base_params)))
    return activations


class AsyncActionDispatcher:
    """Asyncio-native dispatcher: enqueue activations, fire them concurrently.

    Use inside a running event loop::

        dispatcher = AsyncActionDispatcher(num_workers=8)
        await dispatcher.start()
        ...
        result = engine.evaluate(fact)
        await dispatcher.dispatch_result(result, fact)
        ...
        await dispatcher.drain()   # wait for all queued actions
        await dispatcher.stop()
    """

    def __init__(
        self,
        registry: ActionRegistry | None = None,
        num_workers: int = 4,
        max_queue: int = 10_000,
    ) -> None:
        if num_workers <= 0:
            raise ValueError("num_workers must be positive")
        self._registry = registry or _global_registry
        self._num_workers = num_workers
        self._queue: asyncio.Queue[Activation] = asyncio.Queue(maxsize=max_queue)
        self._workers: list[asyncio.Task[None]] = []
        self.stats = DispatchStats()
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(self._num_workers)]

    async def dispatch(self, activation: Activation) -> None:
        """Enqueue a single activation (awaits only if the queue is full)."""
        self.stats.dispatched += 1
        await self._queue.put(activation)

    async def dispatch_result(self, result: Any, facts: dict[str, Any] | None = None) -> None:
        """Enqueue every action implied by an ``EvaluationResult``."""
        for activation in activations_from_result(result, facts):
            await self.dispatch(activation)

    async def drain(self) -> None:
        """Block until all currently-queued activations have been processed."""
        await self._queue.join()

    async def stop(self) -> None:
        """Drain, then cancel workers and shut down."""
        if not self._running:
            return
        await self.drain()
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self, worker_id: int) -> None:
        while True:
            activation = await self._queue.get()
            try:
                await self._fire(activation)
                self.stats.succeeded += 1
            except Exception:
                self.stats.failed += 1
                logger.exception(
                    "Action %r (rule=%s) failed in dispatcher worker %d",
                    activation.action,
                    activation.rule_id,
                    worker_id,
                )
            finally:
                self._queue.task_done()

    async def _fire(self, activation: Activation) -> None:
        meta = self._registry.get(activation.action)
        if meta is None:
            raise ValueError(f"Unknown action: {activation.action}")
        if meta.is_async:
            outcome = await self._registry.execute_async(activation.action, **activation.params)
        else:
            # Run sync (possibly blocking) actions off the event loop thread.
            outcome = await asyncio.to_thread(
                self._registry.execute, activation.action, **activation.params
            )
        # ActionRegistry.execute* swallow handler exceptions and report them as
        # ``{"success": False, "error": ...}``; surface that as a dispatch
        # failure so stats stay accurate.
        if isinstance(outcome, dict) and outcome.get("success") is False:
            raise RuntimeError(f"Action {activation.action!r} failed: {outcome.get('error')}")


class ThreadedActionDispatcher:
    """Run an :class:`AsyncActionDispatcher` on a private background thread.

    Lets *synchronous* evaluation code dispatch actions without managing an
    event loop::

        dispatcher = ThreadedActionDispatcher(num_workers=8)
        dispatcher.start()
        for fact in stream:
            result = engine.evaluate(fact)
            dispatcher.dispatch_result(result, fact)   # non-blocking
        dispatcher.stop()   # drains, then joins the thread
    """

    def __init__(
        self,
        registry: ActionRegistry | None = None,
        num_workers: int = 4,
        max_queue: int = 10_000,
    ) -> None:
        self._registry = registry
        self._num_workers = num_workers
        self._max_queue = max_queue
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._dispatcher: AsyncActionDispatcher | None = None
        self._ready = threading.Event()

    @property
    def stats(self) -> DispatchStats:
        return self._dispatcher.stats if self._dispatcher else DispatchStats()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()  # block until loop + dispatcher are live

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._dispatcher = AsyncActionDispatcher(
            registry=self._registry,
            num_workers=self._num_workers,
            max_queue=self._max_queue,
        )
        self._loop.run_until_complete(self._dispatcher.start())
        self._ready.set()
        self._loop.run_forever()

    def dispatch(self, activation: Activation) -> None:
        """Thread-safe, non-blocking enqueue of a single activation."""
        self._submit(self._dispatcher.dispatch(activation))  # type: ignore[union-attr]

    def dispatch_result(self, result: Any, facts: dict[str, Any] | None = None) -> None:
        """Thread-safe, non-blocking enqueue of all of a result's actions."""
        self._submit(
            self._dispatcher.dispatch_result(result, facts)  # type: ignore[union-attr]
        )

    def drain(self) -> None:
        """Block (the calling thread) until queued actions are processed."""
        self._submit(self._dispatcher.drain()).result()  # type: ignore[union-attr]

    def stop(self) -> None:
        """Drain, stop workers, and join the background thread."""
        if self._thread is None or self._loop is None:
            return
        self._submit(self._dispatcher.stop()).result()  # type: ignore[union-attr]
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
        self._thread = None
        self._loop = None
        self._dispatcher = None
        self._ready.clear()

    def _submit(self, coro: Any) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)
