"""Tests for the typed ErrorPolicy."""

from __future__ import annotations

from typing import Any

import pytest

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import FactPipeline
from fluxrules.pipeline.error_policy import ErrorAction, ErrorPolicy


class FlakyTransform(Transform):
    """Raises ValueError for the first ``fail_times`` calls, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ValueError("transient")
        out = dict(fact)
        out["ok"] = True
        return out

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Flaky", errors_raised=[ValueError])


class Boom(Transform):
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        raise self.exc

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(name="Boom")


class TestErrorPolicyResolution:
    def test_exact_type_match(self):
        policy = ErrorPolicy(routes={ValueError: ErrorAction.SKIP})
        assert policy.decide(ValueError()).action is ErrorAction.SKIP

    def test_base_class_match(self):
        policy = ErrorPolicy(routes={Exception: ErrorAction.SKIP})
        assert policy.decide(ValueError()).action is ErrorAction.SKIP

    def test_default_when_no_match(self):
        policy = ErrorPolicy(default=ErrorAction.FAIL)
        assert policy.decide(KeyError()).action is ErrorAction.FAIL

    def test_specific_overrides_base(self):
        policy = ErrorPolicy(routes={Exception: ErrorAction.FAIL, ValueError: ErrorAction.SKIP})
        assert policy.decide(ValueError()).action is ErrorAction.SKIP

    def test_factory_constructors(self):
        assert ErrorPolicy.fail_fast().default is ErrorAction.FAIL
        assert ErrorPolicy.skip_all().default is ErrorAction.SKIP


class TestErrorPolicyFallback:
    def test_fallback_factory_produces_value(self):
        policy = ErrorPolicy(
            default=ErrorAction.FALLBACK,
            fallback_factory=lambda fact, err: {"fallback": str(err)},
        )
        decision = policy.decide(ValueError("oops"), {})
        assert decision.action is ErrorAction.FALLBACK
        assert decision.fallback == {"fallback": "oops"}

    def test_fallback_without_factory_degrades_to_fail(self):
        policy = ErrorPolicy(default=ErrorAction.FALLBACK)
        assert policy.decide(ValueError()).action is ErrorAction.FAIL


class TestErrorPolicyInPipeline:
    def test_retry_eventually_succeeds(self):
        flaky = FlakyTransform(fail_times=2)
        pipeline = FactPipeline(
            [flaky],
            error_policy=ErrorPolicy(default=ErrorAction.RETRY, max_retries=3),
        )
        assert pipeline({})["ok"] is True
        assert flaky.calls == 3

    def test_retry_exhausted_raises(self):
        flaky = FlakyTransform(fail_times=5)
        pipeline = FactPipeline(
            [flaky],
            error_policy=ErrorPolicy(default=ErrorAction.RETRY, max_retries=2),
        )
        with pytest.raises(ValueError):
            pipeline({})

    def test_fail_policy_raises(self):
        pipeline = FactPipeline([Boom(ValueError("x"))], error_policy=ErrorPolicy.fail_fast())
        with pytest.raises(ValueError):
            pipeline({})

    def test_no_policy_raises(self):
        pipeline = FactPipeline([Boom(ValueError("x"))])
        with pytest.raises(ValueError):
            pipeline({})
