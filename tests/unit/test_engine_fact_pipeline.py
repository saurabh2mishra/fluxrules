"""Engine ``fact_pipeline=``: facts are reshaped before validation and discovery."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from pydantic import BaseModel

from fluxrules import F, FactValidationError, Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import Defaults, FactPipeline, FieldType, Filter, Flatten, Rename, Require
from fluxrules.pipeline.error_policy import ErrorPolicy


class Payment(BaseModel):
    user_id: str
    amount: float


class Order(BaseModel):
    payment: Payment


def _engine(**kwargs) -> PhreakEngine:
    engine = PhreakEngine(**kwargs)
    engine.load_rules(
        [Rule(id=1, name="high_value", conditions=F("amount") > 1000, action="review")]
    )
    return engine


def _normalize() -> FactPipeline:
    return FactPipeline(
        [
            Flatten(),
            Rename({"user_id": ["user.id", "userId"]}),
            FieldType({"amount": float}),
            Require(["user_id", "amount"]),
        ],
        name="normalize_payment",
    )


class TestEngineFactPipeline:
    def test_pipeline_runs_before_evaluation(self):
        engine = _engine(fact_pipeline=_normalize())
        result = engine.evaluate({"user": {"id": "u1"}, "amount": "5000"})
        assert result.fired_rules == [1]

    def test_without_pipeline_raw_fact_does_not_match(self):
        # Sanity check: the string amount needs the pipeline to fire.
        assert _engine().evaluate({"amount": "5000"}).fired_rules == []

    def test_plain_callable_is_accepted(self):
        engine = _engine(fact_pipeline=lambda fact: {**fact, "amount": float(fact["amount"])})
        assert engine.evaluate({"amount": "2000"}).fired_rules == [1]

    def test_model_input_skips_pipeline(self):
        calls = []
        engine = _engine(fact_pipeline=lambda fact: calls.append(fact) or fact)
        assert engine.evaluate(Payment(user_id="u1", amount=2000)).fired_rules == [1]
        assert calls == []

    def test_mapping_input_is_piped(self):
        engine = _engine(fact_pipeline=FactPipeline([FieldType({"amount": float})]))
        assert engine.evaluate(MappingProxyType({"amount": "2000"})).fired_rules == [1]

    def test_nested_schema_instance_with_pipeline_and_validation(self):
        engine = PhreakEngine(
            fact_schema=Order,
            validate_facts="normalize",
            fact_pipeline=FactPipeline([Defaults({"channel": "web"})]),
        )
        engine.load_rules(
            [Rule(id=1, name="big", conditions=F("payment.amount") > 1000, action="review")]
        )
        order = Order(payment=Payment(user_id="u1", amount=5000))
        assert engine.evaluate(order).fired_rules == [1]
        assert engine.evaluate({"payment": {"user_id": "u1", "amount": "5000"}}).fired_rules == [1]

    def test_filtered_fact_returns_empty_result(self):
        pipeline = FactPipeline([Filter(lambda fact: fact.get("country") != "XX")])
        engine = _engine(fact_pipeline=pipeline)
        result = engine.evaluate({"amount": 5000, "country": "XX"})
        assert result.fired_rules == []
        assert result.engine_type == "PhreakEngine"

    def test_skip_error_policy_returns_empty_result(self):
        pipeline = FactPipeline([Require(["amount"])], error_policy=ErrorPolicy.skip_all())
        assert _engine(fact_pipeline=pipeline).evaluate({"other": 1}).fired_rules == []

    def test_pipeline_errors_propagate(self):
        engine = _engine(fact_pipeline=_normalize())
        with pytest.raises(ValueError):
            engine.evaluate({"amount": "5000"})  # no user_id

    def test_pipeline_runs_before_validate_facts(self):
        # Defaults supplies user_id, so strict validation passes.
        pipeline = FactPipeline([Defaults({"user_id": "anon"})])
        engine = _engine(fact_schema=Payment, validate_facts="strict", fact_pipeline=pipeline)
        assert engine.evaluate({"amount": 5000.0}).fired_rules == [1]

    def test_validation_still_rejects_bad_pipeline_output(self):
        pipeline = FactPipeline([Defaults({"channel": "web"})])
        engine = _engine(fact_schema=Payment, validate_facts="strict", fact_pipeline=pipeline)
        with pytest.raises(FactValidationError):
            engine.evaluate({"amount": 5000.0})

    def test_assert_fact_does_not_use_pipeline(self):
        calls = []
        engine = _engine(fact_pipeline=lambda fact: calls.append(fact) or fact)
        engine.assert_fact({"amount": 1})
        assert calls == []
