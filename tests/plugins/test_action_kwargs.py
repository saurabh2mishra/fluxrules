"""Handlers that take ``**kwargs`` can be executed.

The registry used to list ``**kwargs`` as a required parameter named
``kwargs``, so every such handler failed with "Missing required parameter:
kwargs". Handlers that pass a whole fact as keyword arguments rely on this.
"""

from __future__ import annotations

import asyncio

import pytest

from fluxrules.plugins.actions import action, action_registry


@pytest.fixture(autouse=True)
def clean_registry():
    action_registry.reset()
    yield
    action_registry.reset()


def test_kwargs_only_handler_runs():
    @action(name="kw_only")
    def kw_only(**kwargs):
        return kwargs

    result = action_registry.execute("kw_only", amount=5, country="NG")
    assert result["success"] is True
    assert result["result"] == {"amount": 5, "country": "NG"}


def test_kwargs_are_not_listed_as_parameters():
    @action(name="named_plus_kw")
    def named_plus_kw(fact_id: str, *args, **kwargs):
        return {}

    metadata = action_registry.get("named_plus_kw")
    assert [p.name for p in metadata.parameters] == ["fact_id"]
    assert metadata.accepts_extra_kwargs is True


def test_named_parameters_are_still_required_alongside_kwargs():
    @action(name="needs_fact_id")
    def needs_fact_id(fact_id: str, **kwargs):
        return {"fact_id": fact_id, "extra": sorted(kwargs)}

    result = action_registry.execute("needs_fact_id", fact_id="t1", amount=5)
    assert result["result"] == {"fact_id": "t1", "extra": ["amount"]}

    with pytest.raises(ValueError, match="Missing required parameter: fact_id"):
        action_registry.execute("needs_fact_id", amount=5)


def test_handler_without_kwargs_still_rejects_unknown_arguments():
    @action(name="strict")
    def strict(fact_id: str):
        return {"fact_id": fact_id}

    assert action_registry.get("strict").accepts_extra_kwargs is False
    with pytest.raises(ValueError, match="Unknown parameters: amount"):
        action_registry.execute("strict", fact_id="t1", amount=5)


def test_async_kwargs_handler_runs():
    @action(name="async_kw", async_handler=True)
    async def async_kw(**kwargs):
        return kwargs

    result = asyncio.run(action_registry.execute_async("async_kw", amount=5))
    assert result["result"] == {"amount": 5}
