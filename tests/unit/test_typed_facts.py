"""Typed facts: model input, fact_schema checks, fields(), aliases, validation."""

from __future__ import annotations

import dataclasses
from collections import OrderedDict
from types import MappingProxyType
from typing import Annotated, Any, Optional

import pytest
from pydantic import BaseModel, ConfigDict, computed_field
from pydantic import Field as PydanticField
from typing_extensions import TypedDict

from fluxrules import (
    F,
    FactValidationError,
    FluxRulesError,
    InvalidRuleError,
    Rule,
    UnknownFieldError,
    evaluate,
    to_fact_dict,
)
from fluxrules.engine.infrastructure import EvaluationFilter
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.facts import QuarantinedFact, fields, lenient_aliases, schema_info


class Customer(BaseModel):
    model_config = ConfigDict(alias_generator=lenient_aliases())

    user_age: int
    country: str = "US"
    blocked: bool | None = None


class Order(BaseModel):
    amount: float
    customer: Customer
    tags: list[str] = []


@dataclasses.dataclass
class Shipment:
    weight: float
    order: Order | None = None


class Payload(TypedDict):
    amount: float
    meta: dict


class _AttrsField:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeAttrs:
    """Duck-typed stand-in for an attrs class (attrs is not a dependency)."""

    __attrs_attrs__ = (_AttrsField("score"), _AttrsField("label"))
    __annotations__ = {"score": int, "label": str}

    def __init__(self, score: int, label: str) -> None:
        self.score = score
        self.label = label


class FakeStruct:
    """Duck-typed stand-in for a msgspec Struct (msgspec is not a dependency)."""

    __struct_fields__ = ("score",)
    __annotations__ = {"score": int}

    def __init__(self, score: int) -> None:
        self.score = score


def _rule(conditions, rid: int = 1, name: str = "r") -> Rule:
    return Rule(id=rid, name=name, conditions=conditions, action="flag")


def _order(age: int = 30) -> Order:
    return Order(amount=10, customer=Customer(user_age=age))


# ---------------------------------------------------------------------------
# to_fact_dict
# ---------------------------------------------------------------------------


class TestToFactDict:
    def test_dict_is_returned_unchanged(self):
        facts = {"a": 1}
        assert to_fact_dict(facts) is facts

    def test_pydantic_model_flattens_nested_models(self):
        assert to_fact_dict(_order()) == {
            "amount": 10.0,
            "customer.user_age": 30,
            "customer.country": "US",
            "customer.blocked": None,
            "tags": [],
        }

    def test_keys_are_field_names_not_aliases(self):
        class Aliased(BaseModel):
            model_config = ConfigDict(alias_generator=lenient_aliases())
            user_age: int

        assert to_fact_dict(Aliased.model_validate({"userAge": 3})) == {"user_age": 3}

    def test_computed_fields_are_kept(self):
        class WithTotal(BaseModel):
            price: float
            qty: int

            @computed_field
            @property
            def total(self) -> float:
                return self.price * self.qty

        assert to_fact_dict(WithTotal(price=2, qty=3))["total"] == 6

    def test_dataclass_with_nested_pydantic_model(self):
        facts = to_fact_dict(Shipment(weight=1.5, order=_order(40)))
        assert facts["weight"] == 1.5
        assert facts["order.customer.user_age"] == 40

    def test_optional_nested_model_set_to_none_stays_a_key(self):
        assert to_fact_dict(Shipment(weight=1.0)) == {"weight": 1.0, "order": None}

    def test_plain_dict_values_are_not_flattened(self):
        facts = to_fact_dict(Payload(amount=1.0, meta={"k": 1}))
        assert facts == {"amount": 1.0, "meta": {"k": 1}}

    def test_attrs_and_msgspec_by_duck_typing(self):
        assert to_fact_dict(FakeAttrs(5, "x")) == {"score": 5, "label": "x"}
        assert to_fact_dict(FakeStruct(7)) == {"score": 7}

    def test_other_mappings_are_copied(self):
        assert to_fact_dict(OrderedDict(a=1)) == {"a": 1}

    def test_unsupported_input_raises_type_error(self):
        with pytest.raises(TypeError, match="facts must be a dict or a model"):
            to_fact_dict([("a", 1)])


# ---------------------------------------------------------------------------
# Engines accept models (Phase 0)
# ---------------------------------------------------------------------------


class TestEnginesAcceptModels:
    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_phreak_evaluates_a_pydantic_model(self, compile_conditions):
        engine = PhreakEngine(compile_conditions=compile_conditions)
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.evaluate(_order(30)).fired_rules == [1]
        assert engine.evaluate(_order(10)).fired_rules == []

    def test_phreak_evaluates_a_dataclass(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("weight") > 1)])
        assert engine.evaluate(Shipment(weight=2)).fired_rules == [1]

    def test_top_level_evaluate_flattens_nested_models(self):
        assert evaluate(_rule(F("customer.user_age") >= 18), _order(30)).fired_rules == [1]

    def test_dict_input_unchanged(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("amount") > 5)])
        assert engine.evaluate({"amount": 10}).fired_rules == [1]


# ---------------------------------------------------------------------------
# schema_info / fact_schema load-time checks (Phase 1)
# ---------------------------------------------------------------------------


class TestSchemaInfo:
    def test_fields_and_parents(self):
        info = schema_info(Order)
        assert set(info.fields) == {
            "amount",
            "customer.user_age",
            "customer.country",
            "customer.blocked",
            "tags",
        }
        assert info.parents == frozenset({"customer"})
        assert info.kind == "pydantic"
        assert info.name == "Order"

    @pytest.mark.parametrize(
        ("model", "kind"),
        [
            (Shipment, "dataclass"),
            (Payload, "typeddict"),
            (FakeAttrs, "attrs"),
            (FakeStruct, "msgspec"),
        ],
    )
    def test_supported_kinds(self, model, kind):
        assert schema_info(model).kind == kind

    def test_rejects_non_model(self):
        with pytest.raises(TypeError, match="fact_schema must be"):
            schema_info(int)

    def test_self_referencing_model_terminates(self):
        class Node(BaseModel):
            value: int
            parent: Node | None = None

        Node.model_rebuild()
        info = schema_info(Node)
        assert "value" in info.fields
        # The recursive field is a nested model; any path below it is accepted.
        assert "parent" in info.parents and "parent" in info.open_paths
        info.check_field("parent.parent.value")


class TestFactSchemaLoadCheck:
    def test_unknown_field_rejected_at_load(self):
        engine = PhreakEngine(fact_schema=Order)
        with pytest.raises(UnknownFieldError, match="Did you mean 'customer.user_age'"):
            engine.load_rules([_rule(F("customer.userAge") >= 18, name="adult")])

    def test_error_names_the_rule(self):
        engine = PhreakEngine(fact_schema=Order)
        with pytest.raises(UnknownFieldError, match="Rule 'adult'"):
            engine.load_rules([_rule(F("amout") > 1, name="adult")])

    def test_nothing_is_loaded_when_a_rule_is_rejected(self):
        engine = PhreakEngine(fact_schema=Order)
        good = _rule(F("amount") > 1, rid=1)
        bad = _rule(F("nope") > 1, rid=2)
        with pytest.raises(UnknownFieldError):
            engine.load_rules([good, bad])
        assert len(engine.rule_repository) == 0

    def test_exists_fields_are_checked_too(self):
        engine = PhreakEngine(fact_schema=Order)
        engine.load_rules([_rule(F("customer.user_age").exists())])
        with pytest.raises(UnknownFieldError):
            engine.load_rules([_rule(F("cust").exists(), rid=2)])

    def test_nested_model_path_is_refused_with_a_hint(self):
        # A nested model is flattened into its fields, so "customer" is never a
        # key and a rule on it could never match.
        engine = PhreakEngine(fact_schema=Order)
        with pytest.raises(UnknownFieldError, match="nested model") as info:
            engine.load_rules([_rule(F("customer").exists())])
        assert "F('customer.blocked').exists()" in str(info.value)
        assert info.value.suggestion == "customer.blocked"

    def test_dict_rules_are_checked(self):
        engine = PhreakEngine(fact_schema=Order)
        with pytest.raises(UnknownFieldError):
            engine.load_rules(
                [
                    {
                        "id": 1,
                        "name": "d",
                        "conditions": {"type": "condition", "field": "x", "op": "==", "value": 1},
                        "action": "a",
                    }
                ]
            )

    def test_valid_rules_load_and_fire(self):
        engine = PhreakEngine(fact_schema=Order)
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.fact_schema is Order
        assert engine.evaluate(_order(30)).fired_rules == [1]

    def test_error_taxonomy(self):
        assert issubclass(UnknownFieldError, InvalidRuleError)
        assert issubclass(UnknownFieldError, FluxRulesError)
        assert issubclass(UnknownFieldError, AttributeError)
        assert UnknownFieldError.code == "UNKNOWN_FACT_FIELD"


# ---------------------------------------------------------------------------
# fields()
# ---------------------------------------------------------------------------


class TestFieldRefs:
    def test_returns_f_condition(self):
        c = fields(Order)
        assert (c.amount > 5).to_dict() == (F("amount") > 5).to_dict()

    def test_nested_chain(self):
        c = fields(Order)
        assert (c.customer.user_age >= 18).to_dict()["field"] == "customer.user_age"

    def test_item_access(self):
        assert (fields(Order)["amount"] > 1).to_dict()["field"] == "amount"

    def test_typo_raises_with_hint(self):
        with pytest.raises(UnknownFieldError, match="Did you mean 'amount'"):
            fields(Order).amout  # noqa: B018

    def test_hasattr_and_dir(self):
        c = fields(Order)
        assert not hasattr(c, "nope")
        assert dir(c) == ["amount", "customer", "tags"]
        assert dir(c.customer) == ["blocked", "country", "user_age"]

    def test_rule_built_from_fields_passes_schema_check(self):
        c = fields(Order)
        engine = PhreakEngine(fact_schema=Order)
        engine.load_rules([_rule((c.customer.user_age >= 18) & (c.amount > 5))])
        assert engine.evaluate(_order(30)).fired_rules == [1]


# ---------------------------------------------------------------------------
# lenient_aliases
# ---------------------------------------------------------------------------


class TestLenientAliases:
    @pytest.mark.parametrize("key", ["user_age", "userAge", "UserAge", "user-age", "userage"])
    def test_accepts_every_key_style(self, key):
        assert Customer.model_validate({key: 30}).user_age == 30

    def test_unrelated_key_is_not_accepted(self):
        with pytest.raises(Exception, match="user_age|userAge"):
            Customer.model_validate({"age": 30})

    def test_serialization_uses_field_names(self):
        assert Customer(user_age=1).model_dump()["user_age"] == 1


# ---------------------------------------------------------------------------
# validate_facts / on_invalid (Phase 2)
# ---------------------------------------------------------------------------


def _validating(mode: str = "normalize", on_invalid: str = "raise", schema: Any = Customer):
    engine = PhreakEngine(fact_schema=schema, validate_facts=mode, on_invalid=on_invalid)
    engine.load_rules([_rule(F("user_age") >= 18)])
    return engine


class TestValidateFacts:
    @pytest.mark.parametrize("payload", [{"userAge": 30}, {"UserAge": "30"}, {"user-age": 30}])
    def test_normalize_renames_and_coerces(self, payload):
        assert _validating().evaluate(payload).fired_rules == [1]

    def test_strict_rejects_coercion(self):
        engine = _validating("strict")
        assert engine.evaluate({"user_age": 30}).fired_rules == [1]
        with pytest.raises(FactValidationError, match="user_age"):
            engine.evaluate({"user_age": "30"})

    def test_raise_carries_errors(self):
        with pytest.raises(FactValidationError) as info:
            _validating().evaluate({"userAge": "abc"})
        err = info.value
        assert err.schema_name == "Customer"
        assert err.errors[0]["type"] == "int_parsing"
        assert err.code == "FACT_VALIDATION_ERROR"
        assert isinstance(err, ValueError)

    def test_missing_required_field_raises(self):
        with pytest.raises(FactValidationError, match="Field required"):
            _validating().evaluate({"country": "US"})

    def test_skip_returns_empty_result(self, caplog):
        engine = _validating(on_invalid="skip")
        result = engine.evaluate({"userAge": "abc"})
        assert result.fired_rules == []
        assert result.engine_type == "PhreakEngine"
        assert "Skipping invalid fact" in caplog.text
        assert engine.quarantined_facts == []

    def test_quarantine_keeps_fact_and_error(self):
        engine = _validating(on_invalid="quarantine")
        assert engine.evaluate({"userAge": "abc"}).fired_rules == []
        assert engine.evaluate({"userAge": 40}).fired_rules == [1]
        [entry] = engine.quarantined_facts
        assert isinstance(entry, QuarantinedFact)
        assert entry.facts == {"userAge": "abc"}
        assert isinstance(entry.error, FactValidationError)

    def test_quarantine_is_bounded(self):
        engine = _validating(on_invalid="quarantine")
        engine._fact_intake.quarantine = engine._fact_intake.quarantine.__class__(maxlen=2)
        for i in range(5):
            engine.evaluate({"userAge": f"bad{i}"})
        assert [q.facts["userAge"] for q in engine.quarantined_facts] == ["bad3", "bad4"]

    def test_model_instance_skips_validation(self):
        engine = _validating("strict")
        assert engine.evaluate(Customer(user_age=30)).fired_rules == [1]

    def test_nested_payload_is_validated_then_flattened(self):
        engine = PhreakEngine(fact_schema=Order, validate_facts="normalize")
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.evaluate({"amount": 1, "customer": {"userAge": "30"}}).fired_rules == [1]

    def test_dataclass_schema_is_validated(self):
        @dataclasses.dataclass
        class Reading:
            value: float

        engine = PhreakEngine(fact_schema=Reading, validate_facts="normalize")
        engine.load_rules([_rule(F("value") > 1)])
        assert engine.evaluate({"value": "2.5"}).fired_rules == [1]


class TestConstructorValidation:
    def test_validate_requires_schema(self):
        with pytest.raises(ValueError, match="requires fact_schema"):
            PhreakEngine(validate_facts="normalize")

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [({"validate_facts": "lax"}, "validate_facts"), ({"on_invalid": "drop"}, "on_invalid")],
    )
    def test_bad_modes(self, kwargs, match):
        with pytest.raises(ValueError, match=match):
            PhreakEngine(fact_schema=Customer, **kwargs)

    @pytest.mark.parametrize("schema", [FakeAttrs, FakeStruct])
    def test_validation_needs_pydantic_compatible_schema(self, schema):
        with pytest.raises(TypeError, match="needs a schema Pydantic can validate"):
            PhreakEngine(fact_schema=schema, validate_facts="normalize")

    @pytest.mark.parametrize("schema", [FakeAttrs, FakeStruct])
    def test_attrs_and_msgspec_schemas_still_check_rules(self, schema):
        engine = PhreakEngine(fact_schema=schema)
        engine.load_rules([_rule(F("score") > 1)])
        with pytest.raises(UnknownFieldError):
            engine.load_rules([_rule(F("scor") > 1, rid=2)])

    def test_defaults_have_no_schema(self):
        engine = PhreakEngine()
        assert engine.fact_schema is None
        assert engine.quarantined_facts == []


# ---------------------------------------------------------------------------
# Every way a fact reaches the engine (see docs/typed-facts.md)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class OtherShape:
    """A model that is not the engine's fact_schema."""

    user_age: str


class TestFactEntryPaths:
    def test_other_model_into_validating_engine_is_converted_then_validated(self):
        engine = _validating()
        assert engine.evaluate(OtherShape(user_age="40")).fired_rules == [1]
        with pytest.raises(FactValidationError, match="user_age"):
            engine.evaluate(OtherShape(user_age="abc"))

    def test_nested_other_model_is_validated_before_flattening(self):
        @dataclasses.dataclass
        class CustomerShape:
            user_age: str

        @dataclasses.dataclass
        class OrderShape:
            amount: str
            customer: CustomerShape

        engine = PhreakEngine(fact_schema=Order, validate_facts="normalize")
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        shaped = OrderShape(amount="10", customer=CustomerShape(user_age="40"))
        assert engine.evaluate(shaped).fired_rules == [1]

    def test_non_dict_mapping_into_validating_engine(self):
        assert _validating().evaluate(MappingProxyType({"userAge": 40})).fired_rules == [1]

    def test_non_dict_mapping_without_validation(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("user_age") >= 18)])
        assert engine.evaluate(MappingProxyType({"user_age": 40})).fired_rules == [1]

    @pytest.mark.parametrize(
        "call",
        [
            lambda e, f: e.evaluate_by_domain(f, ["default"]),
            lambda e, f: e.evaluate_by_tags(f, []),
            lambda e, f: e.evaluate_all(f),
            lambda e, f: e.evaluate(f, filters=EvaluationFilter()),
        ],
        ids=["by_domain", "by_tags", "all", "filters"],
    )
    def test_convenience_methods_share_the_intake(self, call):
        engine = _validating()
        assert call(engine, {"userAge": "40"}).fired_rules == [1]
        with pytest.raises(FactValidationError):
            call(engine, {"userAge": "abc"})

    @pytest.mark.parametrize("call", [lambda e, f: e.evaluate_all(f)], ids=["all"])
    def test_convenience_methods_accept_models(self, call):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert call(engine, _order(30)).fired_rules == [1]

    @pytest.mark.asyncio
    async def test_evaluate_with_actions_accepts_models(self):
        engine = PhreakEngine()
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        result, _ = await engine.evaluate_with_actions(_order(30))
        assert result.fired_rules == [1]

    def test_streaming_mode_validates_each_fact(self):
        engine = PhreakEngine(fact_schema=Customer, validate_facts="normalize", streaming_mode=True)
        engine.load_rules([_rule(F("user_age") >= 18)])
        assert engine.evaluate({"userAge": 40}).fired_rules == [1]
        assert engine.evaluate({"userAge": 10}).fired_rules == []
        assert engine.evaluate({"user-age": 41}).fired_rules == [1]

    @pytest.mark.parametrize("compile_conditions", [False, True])
    def test_compiled_conditions_with_validation(self, compile_conditions):
        engine = PhreakEngine(
            fact_schema=Customer, validate_facts="normalize", compile_conditions=compile_conditions
        )
        engine.load_rules([_rule((F("user_age") >= 18) & (F("country") == "US"))])
        assert engine.evaluate({"UserAge": "30"}).fired_rules == [1]

    def test_strict_facts_runs_after_conversion(self):
        class Account(BaseModel):
            owner: Customer

        engine = PhreakEngine()
        engine.load_rules([_rule(F("owner.user_age") >= 18)])
        # Nested models are flattened first, so the flat-fact check passes.
        # (List values are still rejected by strict_facts, as before.)
        account = Account(owner=Customer(user_age=30))
        assert engine.evaluate(account, strict_facts=True).fired_rules == [1]

    def test_strict_facts_with_validation(self):
        assert _validating().evaluate({"userAge": 40}, strict_facts=True).fired_rules == [1]

    def test_assert_fact_converts_models(self):
        engine = PhreakEngine()
        fact_id = engine.assert_fact(_order(30))
        stored = engine.working_memory.get_fact(fact_id)
        assert stored["customer.user_age"] == 30

    def test_assert_fact_does_not_validate(self):
        engine = _validating()
        fact_id = engine.assert_fact({"userAge": "abc"})
        assert engine.working_memory.get_fact(fact_id) == {"userAge": "abc"}

    def test_top_level_evaluate_has_no_schema_validation(self):
        # fluxrules.evaluate converts models but has no fact_schema: an aliased
        # key is not renamed, and without a schema a key-style variant is not
        # treated as a typo, so the rule simply does not match.
        assert evaluate(_rule(F("user_age") >= 18), {"userAge": 40}).fired_rules == []


class TestConversionDetails:
    def test_flat_model_returns_its_dump(self):
        assert to_fact_dict(Customer(user_age=1)) == Customer(user_age=1).model_dump()

    def test_any_typed_field_holding_a_model_is_flattened(self):
        class Wrapper(BaseModel):
            payload: Any

        assert to_fact_dict(Wrapper(payload=Customer(user_age=3)))["payload.user_age"] == 3

    def test_any_typed_field_holding_a_dict_is_kept(self):
        class Wrapper(BaseModel):
            payload: Any

        assert to_fact_dict(Wrapper(payload={"k": 1})) == {"payload": {"k": 1}}

    def test_dataclass_inside_pydantic_is_flattened(self):
        class Holder(BaseModel):
            reading: OtherShape

        assert to_fact_dict(Holder(reading=OtherShape(user_age="5"))) == {"reading.user_age": "5"}

    def test_list_of_models_stays_a_list_of_dicts(self):
        class Batch(BaseModel):
            items: list[Customer]

        facts = to_fact_dict(Batch(items=[Customer(user_age=1)]))
        assert facts["items"][0]["user_age"] == 1

    def test_dataclass_containing_list_of_dataclasses(self):
        @dataclasses.dataclass
        class Bag:
            items: list[OtherShape]

        assert to_fact_dict(Bag(items=[OtherShape(user_age="1")])) == {"items": [{"user_age": "1"}]}


# ---------------------------------------------------------------------------
# Model shapes: serialization aliases, Annotated, unions, computed fields
# ---------------------------------------------------------------------------


class AliasedCustomer(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    user_age: int = PydanticField(alias="userAge")


class AliasedOrder(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    order_total: float = PydanticField(alias="orderTotal")
    customer: AliasedCustomer


class Person(BaseModel):
    age: int


class Company(BaseModel):
    employees: int


class Account(BaseModel):
    owner: Person | Company
    backup: Optional[Annotated[Person, "metadata"]] = None  # noqa: UP045
    contact: Person | str = "none"


class Basket(BaseModel):
    price: float
    qty: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> float:
        return self.price * self.qty


class TestModelShapes:
    def test_serialize_by_alias_still_gives_field_names(self):
        order = AliasedOrder(orderTotal=5, customer=AliasedCustomer(userAge=30))
        assert to_fact_dict(order) == {"order_total": 5.0, "customer.user_age": 30}
        engine = PhreakEngine(fact_schema=AliasedOrder)
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.evaluate(order).fired_rules == [1]

    def test_union_of_models_describes_every_branch(self):
        info = schema_info(Account)
        assert {"owner.age", "owner.employees"} <= set(info.fields)
        assert "owner" in info.parents and "owner" not in info.fields

    def test_rules_on_either_union_branch_load_and_fire(self):
        engine = PhreakEngine(fact_schema=Account)
        engine.load_rules(
            [_rule(F("owner.age") >= 18, 1, "adult"), _rule(F("owner.employees") > 100, 2, "big")]
        )
        assert engine.evaluate(Account(owner=Person(age=40))).fired_rules == [1]
        assert engine.evaluate(Account(owner=Company(employees=500))).fired_rules == [2]

    def test_optional_annotated_model_is_a_parent(self):
        info = schema_info(Account)
        assert "backup.age" in info.fields and "backup" in info.parents
        assert to_fact_dict(Account(owner=Person(age=1), backup=Person(age=2)))["backup.age"] == 2

    def test_model_or_plain_value_is_both_leaf_and_parent(self):
        info = schema_info(Account)
        assert "contact" in info.fields and "contact.age" in info.fields

    def test_computed_field_is_in_the_schema(self):
        assert "total" in schema_info(Basket).fields
        engine = PhreakEngine(fact_schema=Basket)
        engine.load_rules([_rule(F("total") > 5)])
        assert engine.evaluate(Basket(price=2, qty=3)).fired_rules == [1]
        assert _rule(fields(Basket).total > 5).conditions == _rule(F("total") > 5).conditions

    def test_other_model_with_computed_field_validates_against_strict_schema(self):
        class StrictBasket(BaseModel):
            model_config = ConfigDict(extra="forbid")

            price: float
            qty: int

        engine = PhreakEngine(fact_schema=StrictBasket, validate_facts="normalize")
        engine.load_rules([_rule(F("price") > 1)])
        # Basket has a computed "total"; it is output, not validation input.
        assert engine.evaluate(Basket(price=2, qty=3)).fired_rules == [1]

    def test_computed_fields_left_out_on_older_pydantic(self, monkeypatch):
        from fluxrules.facts import _dump_without_computed

        real_dump = Basket.model_dump

        def old_model_dump(self, **kwargs):
            if "exclude_computed_fields" in kwargs:  # added in newer Pydantic
                raise TypeError("unexpected keyword argument")
            return real_dump(self, **kwargs)

        monkeypatch.setattr(Basket, "model_dump", old_model_dump)
        assert _dump_without_computed(Basket(price=2, qty=3)) == {"price": 2.0, "qty": 3}


# ---------------------------------------------------------------------------
# Review fixes: parent references, open fields, intake shapes
# ---------------------------------------------------------------------------


class Anything(BaseModel):
    x: Any = None


class TestParentReferences:
    def test_fields_parent_exists_raises_with_hint(self):
        with pytest.raises(UnknownFieldError, match="nested model"):
            fields(Order).customer.exists()

    def test_fields_parent_comparison_raises_instead_of_returning_bool(self):
        with pytest.raises(UnknownFieldError, match="nested model"):
            fields(Order).customer == None  # noqa: B015, E711

    def test_fields_child_of_parent_still_works(self):
        assert (
            _rule(fields(Order).customer.user_age >= 18).conditions
            == _rule(F("customer.user_age") >= 18).conditions
        )

    def test_union_with_plain_value_compares_as_a_field(self):
        assert (
            _rule(fields(Account).contact == "bob").conditions
            == _rule(F("contact") == "bob").conditions
        )
        assert (
            _rule(fields(Account).contact.age > 1).conditions
            == _rule(F("contact.age") > 1).conditions
        )

    def test_unknown_fields_reports_parent(self):
        errors = schema_info(Order).unknown_fields([_rule(F("customer") == 1)])
        assert [e.field for e in errors] == ["customer"]


class TestOpenFields:
    def test_any_field_accepts_dotted_paths(self):
        info = schema_info(Anything)
        assert "x" in info.open_paths
        engine = PhreakEngine(fact_schema=Anything)
        engine.load_rules([_rule(F("x.user_age") >= 18)])
        assert engine.evaluate(Anything(x=Customer(user_age=30))).fired_rules == [1]

    def test_any_field_is_still_a_leaf(self):
        engine = PhreakEngine(fact_schema=Anything)
        engine.load_rules([_rule(F("x") == 5)])
        assert engine.evaluate(Anything(x=5)).fired_rules == [1]


class TypedPayload(TypedDict):
    amount: int


@dataclasses.dataclass
class DcInner:
    age: int


@dataclasses.dataclass
class DcOuter:
    count: int
    inner: DcInner
    tag: str = "t"


class ModelWithDataclass(BaseModel):
    inner: DcInner


class TestIntakeShapes:
    def test_typeddict_schema_validates(self):
        engine = PhreakEngine(fact_schema=TypedPayload, validate_facts="normalize")
        engine.load_rules([_rule(F("amount") > 1)])
        assert engine.evaluate({"amount": "5"}).fired_rules == [1]

    def test_strict_dataclass_schema_accepts_dicts(self):
        engine = PhreakEngine(fact_schema=DcOuter, validate_facts="strict")
        engine.load_rules([_rule(F("inner.age") > 1)])
        assert engine.evaluate({"count": 1, "inner": {"age": 5}}).fired_rules == [1]
        assert engine.evaluate(DcOuter(count=1, inner=DcInner(age=5))).fired_rules == [1]

    def test_strict_dataclass_schema_stays_strict(self):
        engine = PhreakEngine(fact_schema=DcOuter, validate_facts="strict")
        engine.load_rules([_rule(F("count") > 0)])
        with pytest.raises(FactValidationError, match="count"):
            engine.evaluate({"count": "1", "inner": {"age": 5}})

    def test_strict_pydantic_schema_with_nested_dataclass(self):
        engine = PhreakEngine(fact_schema=ModelWithDataclass, validate_facts="strict")
        engine.load_rules([_rule(F("inner.age") > 1)])
        assert engine.evaluate({"inner": {"age": 5}}).fired_rules == [1]

    def test_flat_dotted_fact_validates_against_nested_schema(self):
        engine = PhreakEngine(fact_schema=Order, validate_facts="normalize")
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.evaluate({"amount": 1, "customer.user_age": "30"}).fired_rules == [1]

    def test_flatten_pipeline_then_validation(self):
        from fluxrules.pipeline import FactPipeline, Flatten

        engine = PhreakEngine(
            fact_schema=Order,
            validate_facts="normalize",
            fact_pipeline=FactPipeline([Flatten()]),
        )
        engine.load_rules([_rule(F("customer.user_age") >= 18)])
        assert engine.evaluate({"amount": 1, "customer": {"userAge": 30}}).fired_rules == [1]

    def test_nesting_keeps_keys_that_are_not_nested_models(self):
        from fluxrules.facts import _nest_dotted

        nested = _nest_dotted({"a.b": 1, "customer.age": 2}, frozenset({"customer"}))
        assert nested == {"a.b": 1, "customer": {"age": 2}}


class TreeNode(BaseModel):
    v: int
    child: TreeNode | None = None


@dataclasses.dataclass
class DcCustomer:
    age: int


class TypedOrder(TypedDict):
    customer: DcCustomer


class TestSecondReview:
    def test_validation_does_not_modify_the_callers_input(self):
        engine = PhreakEngine(fact_schema=Order, validate_facts="normalize")
        engine.load_rules([_rule(F("customer.country") == "NG")])
        inner = {"user_age": 30}
        fact = {"amount": 1, "customer": inner, "customer.country": "NG"}
        assert engine.evaluate(fact).fired_rules == [1]
        assert inner == {"user_age": 30}
        assert fact == {"amount": 1, "customer": {"user_age": 30}, "customer.country": "NG"}

    def test_self_referencing_model_accepts_paths_below_it(self):
        engine = PhreakEngine(fact_schema=TreeNode)
        engine.load_rules([_rule(F("child.v") > 1), _rule(F("child.child.v") > 1, rid=2)])
        tree = TreeNode(v=1, child=TreeNode(v=2, child=TreeNode(v=3)))
        assert sorted(engine.evaluate(tree).fired_rules) == [1, 2]

    def test_self_referencing_model_refuses_the_model_path(self):
        with pytest.raises(UnknownFieldError, match="nested model"):
            PhreakEngine(fact_schema=TreeNode).load_rules([_rule(F("child").exists())])

    def test_strict_typeddict_with_nested_dataclass(self):
        engine = PhreakEngine(fact_schema=TypedOrder, validate_facts="strict")
        engine.load_rules([_rule(F("customer").exists())])
        assert engine.evaluate({"customer": {"age": 3}}).fired_rules == [1]

    def test_typeddict_with_unresolvable_annotation(self):
        namespace: dict[str, Any] = {}
        exec(
            "from typing_extensions import TypedDict\n"
            "class Later(TypedDict):\n    item: 'NotDefinedYet'\n",
            namespace,
        )
        assert "item" in schema_info(namespace["Later"]).fields
