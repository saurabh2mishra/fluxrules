"""Tests for the async action dispatcher.

Core guarantee: dispatch does not change *which* rules fire; it only changes
*when and on what thread* their actions run. The set of fired actions seen by
the dispatcher equals the engine's ``actions`` for each fact.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from fluxrules.engine.infrastructure.evaluation_result import EvaluationResult
from fluxrules.engine.runtime import (
    Activation,
    AsyncActionDispatcher,
    ThreadedActionDispatcher,
    activations_from_result,
)
from fluxrules.plugins.actions import ActionRegistry

# activation extraction


def test_activations_pair_rule_with_action():
    result = EvaluationResult(fired_rules=[1, 2], actions=["a", "b"])
    acts = activations_from_result(result, {"x": 1})
    assert [(a.rule_id, a.action) for a in acts] == [(1, "a"), (2, "b")]
    assert all(a.params["facts"] == {"x": 1} for a in acts)


def test_activations_skip_empty_actions():
    result = EvaluationResult(fired_rules=[1, 2], actions=["a", ""])
    acts = activations_from_result(result)
    assert [a.action for a in acts] == ["a"]


def test_activations_fallback_when_unpaired():
    result = EvaluationResult(fired_rules=[1], actions=["a", "b"])
    acts = activations_from_result(result)
    assert [a.action for a in acts] == ["a", "b"]
    assert all(a.rule_id is None for a in acts)


# async dispatcher


def _registry_with_recorder():
    registry = ActionRegistry()
    fired: list[str] = []
    lock = threading.Lock()

    @registry.register(name="sync_act", category="test")
    def sync_act(facts=None):
        with lock:
            fired.append("sync")
        return "ok"

    @registry.register(name="async_act", category="test")
    async def async_act(facts=None):
        await asyncio.sleep(0)
        with lock:
            fired.append("async")
        return "ok"

    return registry, fired


@pytest.mark.asyncio
async def test_async_dispatcher_fires_sync_and_async_actions():
    registry, fired = _registry_with_recorder()
    dispatcher = AsyncActionDispatcher(registry=registry, num_workers=4)
    await dispatcher.start()

    await dispatcher.dispatch(Activation(action="sync_act"))
    await dispatcher.dispatch(Activation(action="async_act"))
    await dispatcher.drain()
    await dispatcher.stop()

    assert sorted(fired) == ["async", "sync"]
    assert dispatcher.stats.dispatched == 2
    assert dispatcher.stats.succeeded == 2
    assert dispatcher.stats.failed == 0


@pytest.mark.asyncio
async def test_async_dispatcher_isolates_failures():
    registry = ActionRegistry()

    @registry.register(name="boom", category="test")
    def boom(facts=None):
        raise RuntimeError("kaboom")

    dispatcher = AsyncActionDispatcher(registry=registry, num_workers=2)
    await dispatcher.start()
    await dispatcher.dispatch(Activation(action="boom"))
    await dispatcher.drain()
    await dispatcher.stop()

    assert dispatcher.stats.failed == 1
    assert dispatcher.stats.succeeded == 0


@pytest.mark.asyncio
async def test_async_dispatcher_unknown_action_counts_as_failure():
    dispatcher = AsyncActionDispatcher(registry=ActionRegistry(), num_workers=1)
    await dispatcher.start()
    await dispatcher.dispatch(Activation(action="nope"))
    await dispatcher.drain()
    await dispatcher.stop()
    assert dispatcher.stats.failed == 1


@pytest.mark.asyncio
async def test_dispatch_result_enqueues_all_actions():
    registry, fired = _registry_with_recorder()
    dispatcher = AsyncActionDispatcher(registry=registry, num_workers=4)
    await dispatcher.start()

    result = EvaluationResult(fired_rules=[1, 2], actions=["sync_act", "async_act"])
    await dispatcher.dispatch_result(result, {"x": 1})
    await dispatcher.drain()
    await dispatcher.stop()

    assert sorted(fired) == ["async", "sync"]
    assert dispatcher.stats.succeeded == 2


# threaded dispatcher


def test_threaded_dispatcher_from_sync_code():
    registry, fired = _registry_with_recorder()
    dispatcher = ThreadedActionDispatcher(registry=registry, num_workers=4)
    dispatcher.start()
    try:
        for _ in range(5):
            dispatcher.dispatch(Activation(action="sync_act"))
            dispatcher.dispatch(Activation(action="async_act"))
        dispatcher.drain()
        assert fired.count("sync") == 5
        assert fired.count("async") == 5
        assert dispatcher.stats.succeeded == 10
    finally:
        dispatcher.stop()


def test_threaded_dispatcher_dispatch_result():
    registry, fired = _registry_with_recorder()
    dispatcher = ThreadedActionDispatcher(registry=registry, num_workers=2)
    dispatcher.start()
    try:
        result = EvaluationResult(fired_rules=[1, 2], actions=["sync_act", "async_act"])
        dispatcher.dispatch_result(result, {"x": 1})
        dispatcher.drain()
        assert sorted(fired) == ["async", "sync"]
    finally:
        dispatcher.stop()
