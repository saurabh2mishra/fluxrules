"""End-to-end tests for the Hybrid Fact Validation architecture.

Exercises the full vertical slice of every module introduced by the Hybrid
approach, from raw intake to engine result:

    raw dict (any source)
        -> Layer 1: FactValidator (structural guard)
        -> Layer 2: FactSchema / validate_facts (Pydantic boundary)
        -> Pipeline: FactPipeline transforms (stream)
        -> ValidatedFactLoader (loader integration)
        -> BaseEngine.evaluate(strict_facts=True) (pre-flight guard)
        -> EvaluationResult (engine output contract)

Correctness assertions are made at every layer boundary to guarantee the
architecture spec from ARCHITECTURAL_CRITIQUE_DICT_VS_PYDANTIC.md is honoured:
no bad data ever reaches the engine on the validated path.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import field_validator

from fluxrules import Rule

# Engine
from fluxrules.engine.phreak import PhreakEngine

# Pipeline and loader
from fluxrules.pipeline import (
    CSVSource,
    Defaults,
    FactLoader,
    FactPipeline,
    FieldType,
    Flatten,
    IterableSource,
    JSONSource,
    Rename,
    Require,
    ValidatedFactLoader,
)

# Schema validation
from fluxrules.pipeline.schema import (
    FactSchema,
    SchemaValidationError,
    validate_facts,
)

# Structural validation
from fluxrules.pipeline.validators import FactValidator, InvalidFactError

# Shared fixtures


class TransactionFact(FactSchema):
    """Canonical fact schema used across all e2e scenarios."""

    user_id: str
    amount: float
    country: str = "US"

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


def _rule(rid: int, field: str, op: str, value: Any, action: str = "", **kw) -> Rule:
    return Rule(
        id=rid,
        name=f"rule_{rid}",
        condition_dsl={"type": "condition", "field": field, "op": op, "value": value},
        action=action or f"action_{rid}",
        **kw,
        persist=False,
    )


def _build_fraud_engine() -> PhreakEngine:
    engine = PhreakEngine()
    engine.load_rules(
        [
            _rule(1, "amount", ">", 10_000, action="flag_fraud", priority=10),
            _rule(2, "amount", ">", 1_000, action="review", priority=5),
            _rule(
                3,
                "country",
                "in",
                ["NG", "RU"],
                action="enhanced_due_diligence",
                priority=3,
            ),
        ]
    )
    return engine


# Layer 1: FactValidator - structural checks, zero deps


class TestLayer1FactValidator:
    def test_valid_flat_dict_passes_unchanged(self):
        fact = {"user_id": "u1", "amount": 500.0, "country": "US"}
        assert FactValidator.validate("test", fact) is fact

    def test_none_values_allowed(self):
        assert FactValidator.validate("test", {"x": None}) == {"x": None}

    def test_non_dict_raises(self):
        with pytest.raises(InvalidFactError, match="result must be a dict"):
            FactValidator.validate("src", [1, 2, 3])

    def test_non_string_key_raises(self):
        with pytest.raises(InvalidFactError, match="all keys must be strings"):
            FactValidator.validate("src", {1: "v"})  # type: ignore[arg-type]

    def test_nested_dict_raises(self):
        with pytest.raises(InvalidFactError, match="facts must be flat"):
            FactValidator.validate("src", {"user": {"id": "u1"}})

    def test_nested_list_raises(self):
        with pytest.raises(InvalidFactError, match="facts must be flat"):
            FactValidator.validate("src", {"tags": ["vip"]})

    def test_is_valid_convenience(self):
        assert FactValidator.is_valid({"a": 1}) is True
        assert FactValidator.is_valid({"a": {"b": 2}}) is False

    def test_error_is_value_error_subclass(self):
        """InvalidFactError must be a ValueError so ErrorPolicy routes it."""
        assert issubclass(InvalidFactError, ValueError)


# Layer 2: FactSchema / validate_facts - Pydantic boundary


class TestLayer2PydanticBoundary:
    def test_valid_fact_coerced_and_returned_as_flat_dict(self):
        raw = {"user_id": "u1", "amount": "1500"}  # amount is a string
        out = validate_facts(TransactionFact, raw)
        assert isinstance(out, dict)
        assert out == {"user_id": "u1", "amount": 1500.0, "country": "US"}

    def test_default_field_injected(self):
        out = validate_facts(TransactionFact, {"user_id": "u1", "amount": 200})
        assert out["country"] == "US"

    def test_output_is_always_plain_flat_dict(self):
        out = validate_facts(TransactionFact, {"user_id": "u1", "amount": 5})
        assert type(out) is dict
        assert all(isinstance(k, str) for k in out)
        # No nested values: FactValidator.validate passes on the output
        FactValidator.validate("layer2", out)

    def test_missing_required_field_raises_schema_error(self):
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_facts(TransactionFact, {"user_id": "u1"})  # missing amount
        assert "amount" in str(exc_info.value)

    def test_unknown_field_rejected_by_default(self):
        with pytest.raises(SchemaValidationError):
            validate_facts(
                TransactionFact,
                {"user_id": "u1", "amount": 10, "typo_field": "x"},
            )

    def test_custom_validator_fires(self):
        with pytest.raises(SchemaValidationError, match="amount must be positive"):
            validate_facts(TransactionFact, {"user_id": "u1", "amount": -1})

    def test_schema_validation_error_is_value_error_subclass(self):
        """SchemaValidationError routes through the same ErrorPolicy as any ValueError."""
        assert issubclass(SchemaValidationError, ValueError)
        assert issubclass(SchemaValidationError, InvalidFactError)

    def test_schema_rejects_structural_garbage_before_pydantic(self):
        """Layer 1 structural check runs first, before Pydantic parses fields."""
        with pytest.raises(InvalidFactError):
            validate_facts(TransactionFact, "not_a_dict")  # type: ignore[arg-type]


# Layer 3: ValidatedFactLoader - stream-level boundary


class TestLayer3ValidatedFactLoader:
    def _normalize_pipeline(self) -> FactPipeline:
        return FactPipeline(
            [
                Flatten(),
                Rename({"user_id": ["userId", "user_id"]}),
                FieldType({"amount": float}),
                Defaults({"country": "US"}),
                Require(["user_id", "amount"]),
            ]
        )

    def test_valid_records_pass_through_with_coercion(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u1", "amount": "1500", "country": "NG"}]),
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
        )
        out = list(loader)
        assert out == [{"user_id": "u1", "amount": 1500.0, "country": "NG"}]

    def test_invalid_records_collected_not_raised(self):
        loader = ValidatedFactLoader(
            source=IterableSource(
                [
                    {"user_id": "u1", "amount": "500"},  # valid
                    {"user_id": "u2"},  # missing amount
                    {"user_id": "u3", "amount": -10},  # fails @field_validator
                ]
            ),
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
            on_error="collect",
        )
        out = list(loader)
        assert len(out) == 1
        assert out[0]["user_id"] == "u1"
        assert len(loader.dead_letter) == 2

    def test_invalid_records_skipped_silently(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u2"}]),  # missing amount
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
            on_error="skip",
        )
        assert list(loader) == []
        assert loader.dead_letter == []

    def test_invalid_records_raise_when_policy_is_raise(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u1"}]),  # missing amount
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
            on_error="raise",
        )
        with pytest.raises(SchemaValidationError):
            list(loader)

    def test_schema_none_is_identical_to_base_fact_loader(self):
        """schema=None must be a true drop-in for FactLoader."""
        records = [{"user_id": "u1", "amount": 10.0}]
        base = list(FactLoader(IterableSource(records), self._normalize_pipeline()))
        validated = list(
            ValidatedFactLoader(IterableSource(records), self._normalize_pipeline(), schema=None)
        )
        assert base == validated

    def test_json_source_through_validated_loader(self):
        import json

        payload = json.dumps([{"user_id": "u_json", "amount": 200.0, "country": "DE"}])
        loader = ValidatedFactLoader(
            source=JSONSource(payload),
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
        )
        out = list(loader)
        assert out[0]["user_id"] == "u_json"

    def test_csv_source_with_string_amounts_coerced(self):
        csv_text = "user_id,amount,country\nu_csv,750,FR\n"
        loader = ValidatedFactLoader(
            source=CSVSource(csv_text),
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
        )
        out = list(loader)
        assert out[0]["amount"] == 750.0  # coerced from CSV string

    def test_batching_works_on_validated_loader(self):
        loader = ValidatedFactLoader(
            source=IterableSource(
                [{"user_id": f"u{i}", "amount": float(i * 100)} for i in range(1, 6)]
            ),
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
        )
        batches = list(loader.batch(2))
        assert [len(b) for b in batches] == [2, 2, 1]

    def test_dead_letter_records_contain_raw_and_error(self):
        loader = ValidatedFactLoader(
            source=IterableSource([{"user_id": "u1"}]),  # missing amount
            pipeline=self._normalize_pipeline(),
            schema=TransactionFact,
            on_error="collect",
        )
        list(loader)
        entry = loader.dead_letter[0]
        assert "raw" in entry
        assert "error" in entry
        assert entry["raw"] == {"user_id": "u1"}


# Layer 4: Engine pre-flight - strict_facts guard


class TestLayer4EnginePreflight:
    def test_default_off_allows_nested_data(self):
        """strict_facts=False (default) stays backward-compatible."""
        engine = PhreakEngine()
        result = engine.evaluate({"user": {"id": "u1"}})
        assert result.fired_rules == []

    def test_strict_facts_rejects_nested_dict(self):
        engine = PhreakEngine()
        with pytest.raises(InvalidFactError, match="facts must be flat"):
            engine.evaluate({"user": {"id": "u1"}}, strict_facts=True)

    def test_strict_facts_rejects_nested_list(self):
        engine = PhreakEngine()
        with pytest.raises(InvalidFactError, match="facts must be flat"):
            engine.evaluate({"tags": ["vip"]}, strict_facts=True)

    def test_strict_facts_rejects_non_dict(self):
        engine = PhreakEngine()
        with pytest.raises(InvalidFactError):
            engine.evaluate("bad", strict_facts=True)  # type: ignore[arg-type]

    def test_strict_facts_passes_flat_dict_and_evaluates(self):
        engine = _build_fraud_engine()
        result = engine.evaluate(
            {"user_id": "u1", "amount": 15_000.0, "country": "US"},
            strict_facts=True,
        )
        assert 1 in result.fired_rules  # amount > 10_000
        assert 2 in result.fired_rules  # amount > 1_000
        assert 3 not in result.fired_rules  # country not in ["NG","RU"]

    def test_engine_accepts_strict_facts_single_rule(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(1, "amount", ">", 100)])
        result = engine.evaluate({"amount": 500}, strict_facts=True)
        assert 1 in result.fired_rules


# Full vertical slice: all validation stages working together


class TestFullHybridSlice:
    """
    Complete data flow:
      raw messy source
        → ValidatedFactLoader (schema boundary + pipeline)
        → engine.evaluate(strict_facts=True)
        → EvaluationResult
    """

    def _normalize(self) -> FactPipeline:
        return FactPipeline(
            [
                Flatten(),
                Rename(
                    {
                        "user_id": ["userId", "user.id", "user_id"],
                        "amount": ["order.amount", "amount_cents", "amount"],
                        "country": ["device.country", "country_code", "country"],
                    }
                ),
                FieldType({"amount": float}),
                Defaults({"country": "US"}),
                Require(["user_id", "amount"]),
            ]
        )

    def test_nested_json_intake_fires_rules_end_to_end(self):
        """
        The Hybrid architecture validates *after* the pipeline normalises the
        fact.  Flatten+Rename keeps both the original dotted keys and the
        canonical renamed ones in the output dict (all still flat strings).
        The schema used here sets ``extra='allow'`` so those pass-through keys
        are accepted; the canonical fields are still typed and validated.

        Flow:
            raw nested → FactLoader (Flatten+Rename+...) → flat dict (6 keys)
                       → ValidatedFactLoader(schema, extra='allow') → engine
        """
        from pydantic import ConfigDict as _CD

        class _LooseTxFact(FactSchema):
            """TransactionFact that accepts extra dotted pass-through keys."""

            model_config = _CD(extra="allow")
            user_id: str
            amount: float
            country: str = "US"

        engine = _build_fraud_engine()
        raw_nested = [
            {
                "user": {"id": "u_vip"},
                "order": {"amount": 50_000.0},
                "device": {"country": "NG"},
            }
        ]
        # Stage 1: flatten+rename to flat dict
        normalised = list(FactLoader(IterableSource(raw_nested), self._normalize()))
        assert len(normalised) == 1
        flat = normalised[0]
        # Both original dotted keys and canonical aliases are present (all flat)
        assert flat["user_id"] == "u_vip"
        assert flat["amount"] == 50_000.0
        assert flat["country"] == "NG"

        # Stage 2: validate with schema that permits the extra pass-through keys
        loader = ValidatedFactLoader(
            source=IterableSource(normalised),
            pipeline=FactPipeline([Require(["user_id", "amount"])]),
            schema=_LooseTxFact,
        )
        facts = list(loader)
        assert len(facts) == 1
        result = engine.evaluate(facts[0], strict_facts=True)
        assert 1 in result.fired_rules  # amount(50000) > 10_000
        assert 2 in result.fired_rules  # amount(50000) > 1_000
        assert 3 in result.fired_rules  # country == NG

    def test_invalid_records_rejected_before_engine_ever_called(self):
        engine = _build_fraud_engine()
        raw_records = [
            {"user_id": "ok", "amount": 2_000, "country": "US"},  # valid
            {"user_id": "bad"},  # missing amount
            {"user_id": "neg", "amount": -500},  # fails validator
        ]
        loader = ValidatedFactLoader(
            source=IterableSource(raw_records),
            pipeline=self._normalize(),
            schema=TransactionFact,
            on_error="collect",
        )
        results = [engine.evaluate(f, strict_facts=True) for f in loader]
        # Only the first record reached the engine
        assert len(results) == 1
        assert 2 in results[0].fired_rules  # amount > 1_000
        # Two bad records were caught before the engine
        assert len(loader.dead_letter) == 2

    def test_output_dict_always_flat_at_every_boundary(self):
        """Every fact the engine sees must pass FactValidator."""
        engine = _build_fraud_engine()
        loader = ValidatedFactLoader(
            source=IterableSource(
                [{"user_id": f"u{i}", "amount": float(i * 100)} for i in range(1, 4)]
            ),
            pipeline=self._normalize(),
            schema=TransactionFact,
        )
        for fact in loader:
            # Structural check: Layer 1 guard passes on every fact
            FactValidator.validate("e2e_check", fact)
            # Engine accepts and processes without strict_facts error
            engine.evaluate(fact, strict_facts=True)

    def test_error_policy_on_pipeline_vs_schema_are_independent(self):
        """
        Schema validation failures are caught at Layer 2 (before the pipeline).
        Pipeline failures (e.g. Require) are caught by the loader error policy.
        Both are routed to dead_letter with on_error='collect'.
        """
        loader = ValidatedFactLoader(
            source=IterableSource(
                [
                    {"user_id": "u1", "amount": 500},  # valid all the way
                    {"user_id": "u2"},  # schema fail: missing amount
                    {
                        "user_id": "u3",
                        "amount": 200,
                        "extra": 1,
                    },  # schema fail: unknown field
                ]
            ),
            pipeline=self._normalize(),
            schema=TransactionFact,
            on_error="collect",
        )
        out = list(loader)
        assert len(out) == 1
        assert out[0]["user_id"] == "u1"
        assert len(loader.dead_letter) == 2

    def test_csv_intake_amounts_coerced_rules_fire_correctly(self):
        csv_text = (
            "user_id,amount,country\n"
            "u_csv_1,15000,NG\n"
            "u_csv_2,50,US\n"  # amount too low to fire any rule
        )
        engine = _build_fraud_engine()
        loader = ValidatedFactLoader(
            source=CSVSource(csv_text),
            pipeline=self._normalize(),
            schema=TransactionFact,
        )
        all_facts = list(loader)
        assert len(all_facts) == 2
        r1 = engine.evaluate(all_facts[0], strict_facts=True)
        assert 1 in r1.fired_rules  # 15000 > 10000
        assert 3 in r1.fired_rules  # country=NG
        r2 = engine.evaluate(all_facts[1], strict_facts=True)
        assert r2.fired_rules == []  # 50 fires nothing


# Architecture contract: validated path never reaches engine with bad data


class TestArchitectureContracts:
    """Assert the guarantees stated in ARCHITECTURAL_CRITIQUE_DICT_VS_PYDANTIC.md."""

    def test_module_a_is_dependency_free(self):
        """Layer 1 imports only stdlib - no pydantic, no external packages."""
        from fluxrules.pipeline import validators as mod

        # Must not have pydantic in its namespace
        assert not hasattr(mod, "BaseModel")

    def test_module_b_output_passes_module_a_check(self):
        """validate_facts() → dict must always be structurally valid (defense in depth)."""
        out = validate_facts(TransactionFact, {"user_id": "u1", "amount": 9})
        # Layer 1 re-validation: FactSchema.to_facts() already calls FactValidator,
        # but we assert it explicitly here as the architecture contract.
        assert FactValidator.validate("contract", out) == out

    def test_invalid_fact_error_is_routable_by_error_policy(self):
        """Both InvalidFactError and SchemaValidationError must be ValueError subclasses."""
        assert issubclass(InvalidFactError, ValueError)
        assert issubclass(SchemaValidationError, ValueError)

    def test_engine_result_type_unchanged_by_strict_flag(self):
        """strict_facts=True must not change the EvaluationResult shape."""

        engine = _build_fraud_engine()
        r_default = engine.evaluate({"user_id": "u1", "amount": 500.0})
        r_strict = engine.evaluate({"user_id": "u1", "amount": 500.0}, strict_facts=True)
        assert type(r_default) is type(r_strict)
        assert r_default.fired_rules == r_strict.fired_rules

    def test_validated_loader_output_is_valid_engine_input(self):
        """Every fact emitted by ValidatedFactLoader passes strict_facts=True."""
        engine = _build_fraud_engine()
        loader = ValidatedFactLoader(
            source=IterableSource(
                [{"user_id": f"u{i}", "amount": float(i * 300)} for i in range(1, 6)]
            ),
            pipeline=FactPipeline(
                [
                    FieldType({"amount": float}),
                    Defaults({"country": "US"}),
                    Require(["user_id", "amount"]),
                ]
            ),
            schema=TransactionFact,
        )
        for fact in loader:
            # This must NOT raise - the hybrid path guarantees valid engine input
            engine.evaluate(fact, strict_facts=True)
