"""Typed facts: less common shapes and error paths.

Covers the parts of fluxrules.facts that the main typed-facts tests do not:
containers of models, legacy objects, schema file loading errors, every
comparison on a field reference, dotted-key merging, and strict-mode mirrors of
dataclasses inside generic types.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Annotated, Generic, NotRequired, Optional, TypeVar

import pytest
from pydantic import BaseModel
from typing_extensions import TypedDict

from fluxrules import F, FactValidationError, Rule, to_fact_dict
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.facts import (
    _mirror_annotation,
    _nest_dotted,
    _strict_mirror,
    fields,
    load_schema,
    referenced_fields,
)


def _rule(conditions, rid: int = 1) -> Rule:
    return Rule(id=rid, name=f"r{rid}", conditions=conditions, action="flag")


class Item(BaseModel):
    sku: str


@dataclasses.dataclass
class Basket:
    items: list[Item]
    pair: tuple[Item, Item]
    by_name: dict[str, Item]
    created: datetime | None = None


class LegacyModel:
    """Duck-typed stand-in for a Pydantic v1 model (.dict() and __fields__)."""

    __fields__ = {"amount": None}

    def __init__(self, amount: object) -> None:
        self.amount = amount

    def dict(self) -> dict[str, object]:
        return {"amount": self.amount}


class Amount(BaseModel):
    amount: int


class Person(BaseModel):
    age: int


class Contact(BaseModel):
    contact: Person | str = "none"


class TestConversion:
    def test_models_inside_containers_become_plain_dicts(self):
        created = datetime(2026, 1, 1)
        basket = Basket(
            items=[Item(sku="a")],
            pair=(Item(sku="b"), Item(sku="c")),
            by_name={"d": Item(sku="d")},
            created=created,
        )
        assert to_fact_dict(basket) == {
            "items": [{"sku": "a"}],
            "pair": ({"sku": "b"}, {"sku": "c"}),
            "by_name": {"d": {"sku": "d"}},
            "created": created,  # other values are kept as they are
        }

    def test_pydantic_v1_style_object_uses_its_dict_method(self):
        assert to_fact_dict(LegacyModel(5)) == {"amount": 5}

    def test_legacy_object_is_validated_by_a_validating_engine(self):
        engine = PhreakEngine(fact_schema=Amount, validate_facts="normalize")
        engine.load_rules([_rule(F("amount") > 1)])
        assert engine.evaluate(LegacyModel("5")).fired_rules == [1]
        with pytest.raises(FactValidationError):
            engine.evaluate(LegacyModel("lots"))


class TestLoadSchemaFiles:
    def test_same_file_is_imported_once(self, tmp_path):
        (tmp_path / "models.py").write_text(
            "from pydantic import BaseModel\n\nclass M(BaseModel):\n    x: int\n"
        )
        first = load_schema("models.py:M", base_dir=tmp_path)
        assert load_schema("models.py:M", base_dir=tmp_path) is first

    def test_absolute_file_path(self, tmp_path):
        (tmp_path / "abs_models.py").write_text(
            "from pydantic import BaseModel\n\nclass M(BaseModel):\n    x: int\n"
        )
        model = load_schema(f"{tmp_path / 'abs_models.py'}:M", base_dir="/nowhere")
        assert model.__name__ == "M"

    def test_file_python_cannot_load_is_refused(self, tmp_path):
        (tmp_path / "schemas").mkdir()
        (tmp_path / "schemas" / "models.txt").write_text("x = 1\n")
        with pytest.raises(ImportError, match="cannot load fact schema file"):
            load_schema("schemas/models.txt:M", base_dir=tmp_path)


class TestReferencedFields:
    def test_non_dict_nodes_are_ignored(self):
        assert referenced_fields(["junk", {"type": "condition", "field": "a"}]) == ["a"]


class TestFieldReferences:
    def test_dunder_lookups_are_plain_attribute_errors(self):
        assert getattr(fields(Amount), "__wrapped__", None) is None

    def test_the_model_itself_is_not_a_field(self):
        with pytest.raises(TypeError, match="is not a field"):
            fields(Amount) == 1  # noqa: B015

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            (lambda c: c != "x", F("contact") != "x"),
            (lambda c: c < "x", F("contact") < "x"),
            (lambda c: c <= "x", F("contact") <= "x"),
            (lambda c: c > "x", F("contact") > "x"),
            (lambda c: c >= "x", F("contact") >= "x"),
        ],
        ids=["ne", "lt", "le", "gt", "ge"],
    )
    def test_every_comparison_on_a_field_that_can_hold_a_value(self, build, expected):
        built = build(fields(Contact).contact)
        assert _rule(built).conditions == _rule(expected).conditions


class TestNestDotted:
    def test_dotted_key_before_the_nested_dict_wins(self):
        inner = {"age": 1, "name": "nested"}
        facts = {"customer.name": "dotted", "customer": inner}
        out = _nest_dotted(facts, frozenset({"customer"}))
        assert out == {"customer": {"age": 1, "name": "dotted"}}
        assert inner == {"age": 1, "name": "nested"}  # the input is not modified

    def test_several_dotted_keys_share_one_nested_dict(self):
        out = _nest_dotted({"customer.age": 1, "customer.name": "x"}, frozenset({"customer"}))
        assert out == {"customer": {"age": 1, "name": "x"}}

    def test_nothing_to_nest_returns_the_input(self):
        facts = {"a": 1}
        assert _nest_dotted(facts, frozenset({"customer"})) is facts


# ---------------------------------------------------------------------------
# Strict-mode mirrors of dataclasses inside generic types
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Part:
    code: int


@dataclasses.dataclass
class Order:
    parts: list[Part] = dataclasses.field(default_factory=list)
    main: Optional[Part] = None  # noqa: UP045
    tagged: Annotated[Part, "meta"] = dataclasses.field(default_factory=lambda: Part(0))


class OrderDict(TypedDict):
    part: Part
    spare: NotRequired[Part]


class Tree(BaseModel):
    v: int
    child: Tree | None = None


class TestStrictMirrors:
    def test_dataclass_in_list_optional_and_annotated(self):
        engine = PhreakEngine(fact_schema=Order, validate_facts="strict")
        engine.load_rules([_rule(F("main.code") > 1)])
        fact = {"parts": [{"code": 1}], "main": {"code": 5}, "tagged": {"code": 2}}
        assert engine.evaluate(fact).fired_rules == [1]
        with pytest.raises(FactValidationError):
            engine.evaluate({"parts": [{"code": "1"}]})

    def test_default_factory_is_kept(self):
        mirror = _strict_mirror(Order)
        assert mirror.model_validate({}, strict=True).parts == []

    def test_typeddict_with_not_required_dataclass(self):
        engine = PhreakEngine(fact_schema=OrderDict, validate_facts="strict")
        engine.load_rules([_rule(F("part").exists())])
        assert engine.evaluate({"part": {"code": 1}}).fired_rules == [1]
        assert engine.evaluate({"part": {"code": 1}, "spare": {"code": 2}}).fired_rules == [1]

    def test_self_referencing_model_without_dataclasses_is_not_mirrored(self):
        assert _strict_mirror(Tree) is Tree
        engine = PhreakEngine(fact_schema=Tree, validate_facts="strict")
        engine.load_rules([_rule(F("child.v") > 1)])
        assert engine.evaluate({"v": 1, "child": {"v": 2}}).fired_rules == [1]

    def test_annotations_without_dataclasses_are_unchanged(self):
        assert _mirror_annotation(list[int]) == list[int]

    def test_generic_that_rejects_the_mirror_keeps_the_original(self):
        T = TypeVar("T")

        class OnlyDataclasses(Generic[T]):
            def __class_getitem__(cls, item):
                if not dataclasses.is_dataclass(item):
                    raise TypeError("dataclasses only")
                return super().__class_getitem__(item)

        annotation = OnlyDataclasses[Part]
        assert _mirror_annotation(annotation) is annotation
