"""Typed facts: models as engine input, fact schemas, and checked field references.

Facts reach an engine as a flat ``dict``. This module lets callers bring a typed
model instead, and lets an engine check rules against that model:

- :func:`to_fact_dict` turns a Pydantic model, dataclass, attrs class or msgspec
  ``Struct`` into the flat dict the engine reads. Nested models become dotted
  keys (``customer.age``), matching the ``Flatten`` transform.
- :func:`schema_info` describes a model class as the set of flat field paths a
  rule may reference. ``PhreakEngine(fact_schema=Model)`` uses it to refuse, at
  ``load_rules``, any rule naming a field the model does not have.
- :func:`fields` gives checked field references for authoring rules:
  ``fields(Customer).age >= 18`` builds the same condition as ``F("age") >= 18``,
  but a typo fails on the spot.
- :func:`lenient_aliases` is a Pydantic alias generator that accepts a field in
  snake_case, camelCase, PascalCase, kebab-case or all-lowercase form.

Model libraries are detected by duck typing (``model_fields``,
``__dataclass_fields__``, ``__attrs_attrs__``, ``__struct_fields__``), so attrs
and msgspec are supported without being dependencies.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import importlib.util
import logging
import sys
import types
import typing
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fluxrules.domain.errors import UnknownFieldError

logger = logging.getLogger(__name__)

__all__ = [
    "FactSchemaInfo",
    "QuarantinedFact",
    "fields",
    "lenient_aliases",
    "load_schema",
    "schema_info",
    "to_fact_dict",
]


# Model detection


def _model_kind(tp: Any) -> str | None:
    """Return which model library *tp* (a class) belongs to, or ``None``."""
    if not isinstance(tp, type):
        return None
    if isinstance(getattr(tp, "model_fields", None), dict) and hasattr(tp, "model_validate"):
        return "pydantic"
    if dataclasses.is_dataclass(tp):
        return "dataclass"
    if hasattr(tp, "__attrs_attrs__"):
        return "attrs"
    if hasattr(tp, "__struct_fields__"):
        return "msgspec"
    # typing.is_typeddict misses typing_extensions.TypedDict (which Pydantic
    # requires on Python < 3.12), so check the shape both produce.
    if issubclass(tp, dict) and hasattr(tp, "__required_keys__"):
        return "typeddict"
    return None


def _cls(obj: Any) -> Any:
    """``type(obj)``, typed as ``Any`` so it can key the per-class caches."""
    return type(obj)


@functools.lru_cache(maxsize=1024)
def _type_kind(tp: Any) -> str | None:
    kind = _model_kind(tp)
    # A TypedDict instance is a plain dict at runtime.
    return None if kind == "typeddict" else kind


def _instance_kind(obj: Any) -> str | None:
    return _type_kind(_cls(obj))


@functools.lru_cache(maxsize=1024)
def _instance_field_names(tp: Any, kind: str) -> tuple[str, ...]:
    """Field names of a model class, cached for per-instance conversion."""
    return tuple(_field_names(tp, kind))


def _field_names(tp: type, kind: str) -> list[str]:
    if kind == "pydantic":
        return list(tp.model_fields)  # type: ignore[attr-defined]
    if kind == "dataclass":
        return [f.name for f in dataclasses.fields(tp)]
    if kind == "attrs":
        return [a.name for a in tp.__attrs_attrs__]  # type: ignore[attr-defined]
    if kind == "msgspec":
        return list(tp.__struct_fields__)  # type: ignore[attr-defined]
    return list(typing.get_type_hints(tp))


def _field_types(tp: type, kind: str) -> dict[str, Any]:
    names = _field_names(tp, kind)
    if kind == "pydantic":
        return {n: tp.model_fields[n].annotation for n in names}  # type: ignore[attr-defined]
    try:
        hints = typing.get_type_hints(tp)
    except Exception:  # unresolvable forward references: treat as untyped
        hints = {}
    return {n: hints.get(n, Any) for n in names}


def _nested_model(annotation: Any) -> type | None:
    """Return the model class an annotation holds, unwrapping ``Optional``."""
    if _model_kind(annotation) not in (None, "typeddict"):
        return annotation
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _nested_model(args[0])
    return None


# Instance -> flat dict


_SCALARS = (str, int, float, bool, type(None))


def _plain(value: Any) -> Any:
    """Convert models nested inside containers to plain dicts (not flattened)."""
    if isinstance(value, _SCALARS):
        return value
    kind = _instance_kind(value)
    if kind == "pydantic":
        return value.model_dump()
    if kind is not None:
        return {n: _plain(getattr(value, n)) for n in _instance_field_names(_cls(value), kind)}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_plain(v) for v in value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _mentions_model(annotation: Any) -> bool:
    """Whether a field with this annotation can hold a model instance."""
    if annotation is Any or annotation is object:
        return True
    if _model_kind(annotation) not in (None, "typeddict"):
        return True
    return any(_mentions_model(arg) for arg in typing.get_args(annotation))


@functools.lru_cache(maxsize=1024)
def _model_valued_fields(tp: Any) -> frozenset[str]:
    """Names of a Pydantic model's fields that can hold a nested model.

    Computed once per class, so converting an instance only inspects the
    attributes that might need flattening.
    """
    return frozenset(
        name
        for name, annotation in _field_types(tp, "pydantic").items()
        if _mentions_model(annotation)
    )


def _flatten_pydantic(obj: Any, dumped: dict[str, Any], prefix: str, out: dict[str, Any]) -> None:
    """Flatten one ``model_dump()`` result, expanding nested models into dotted keys.

    ``model_dump`` runs once, at the top: it already dumped every nested model,
    keeping computed fields and custom serializers. Only fields that can hold a
    model are checked against the live attribute, so a plain ``dict`` field is
    kept as a value.
    """
    nested = _model_valued_fields(_cls(obj))
    for name, value in dumped.items():
        if name in nested and type(value) is dict:
            attr = getattr(obj, name, None)
            kind = _instance_kind(attr)
            if kind == "pydantic":
                _flatten_pydantic(attr, value, f"{prefix}{name}.", out)
                continue
            if kind is not None:
                _flatten_into(attr, kind, f"{prefix}{name}.", out)
                continue
        out[f"{prefix}{name}"] = value


def _flatten_into(obj: Any, kind: str, prefix: str, out: dict[str, Any]) -> None:
    if kind == "pydantic":
        _flatten_pydantic(obj, obj.model_dump(), prefix, out)
        return
    for name in _instance_field_names(_cls(obj), kind):
        value = getattr(obj, name)
        value_kind = _instance_kind(value)
        if value_kind is not None:
            _flatten_into(value, value_kind, f"{prefix}{name}.", out)
        else:
            out[f"{prefix}{name}"] = _plain(value)


def to_fact_dict(facts: Any) -> dict[str, Any]:
    """Return *facts* as the flat dict an engine evaluates.

    - A ``dict`` is returned unchanged (no copy), so the plain-dict path costs
      nothing.
    - A Pydantic v2 model, dataclass, attrs class or msgspec ``Struct`` is
      converted field by field. Nested models become dotted keys:
      ``Order(customer=Customer(age=30))`` gives ``{"customer.age": 30}``.
      Plain ``dict`` values are kept as values, not flattened.
    - Any other ``Mapping`` is copied into a ``dict``; a Pydantic v1 model is
      converted with ``.dict()``.

    Keys are the models' Python field names, not their aliases, because rules
    reference field names.

    Raises:
        TypeError: for anything else.
    """
    if type(facts) is dict:
        return facts
    kind = _instance_kind(facts)
    if kind == "pydantic":
        dumped = facts.model_dump()
        if not _model_valued_fields(_cls(facts)):
            return dumped  # flat model: the dump is already the fact dict
        out: dict[str, Any] = {}
        _flatten_pydantic(facts, dumped, "", out)
        return out
    if kind is not None:
        out = {}
        _flatten_into(facts, kind, "", out)
        return out
    if isinstance(facts, Mapping):
        return dict(facts)
    legacy_dict = getattr(facts, "dict", None)
    if callable(legacy_dict) and hasattr(facts, "__fields__"):  # Pydantic v1
        return legacy_dict()
    raise TypeError(
        f"facts must be a dict or a model (Pydantic, dataclass, attrs, msgspec), "
        f"got {type(facts).__name__}. Convert your object to a dict first."
    )


# Schema description


@dataclass(frozen=True)
class FactSchemaInfo:
    """A model class described as the flat field paths a rule may reference.

    Attributes:
        model: the model class.
        kind: ``"pydantic"``, ``"dataclass"``, ``"attrs"``, ``"msgspec"`` or
            ``"typeddict"``.
        fields: flat field path -> annotation, for every leaf field. Nested
            models contribute dotted paths (``customer.age``).
        parents: dotted prefixes of nested models (``customer``). Valid in a
            rule (for example ``F("customer").exists()``) but not leaves.
    """

    model: type
    kind: str
    fields: Mapping[str, Any]
    parents: frozenset[str]

    @property
    def name(self) -> str:
        return self.model.__name__

    @property
    def known(self) -> frozenset[str]:
        """Every field path a rule may reference (leaves and parents)."""
        return frozenset(self.fields) | self.parents

    def check_field(self, field: str, *, rule: str | None = None) -> None:
        """Raise :class:`UnknownFieldError` unless *field* is in the schema."""
        if field not in self.fields and field not in self.parents:
            raise UnknownFieldError.for_field(field, self.name, sorted(self.known), rule=rule)

    def check_rules(self, rules: Iterable[Any]) -> None:
        """Check every field referenced by *rules* against this schema.

        Accepts the same rule shapes as ``load_rules`` (``Rule`` objects or
        dicts). Raises on the first unknown field, in rule order.
        """
        for error in self._iter_unknown(rules):
            raise error

    def unknown_fields(self, rules: Iterable[Any]) -> list[UnknownFieldError]:
        """Every unknown field referenced by *rules*, in rule order.

        Like :meth:`check_rules` but collects instead of raising, so a CI check
        can report all problems at once.
        """
        return list(self._iter_unknown(rules))

    def _iter_unknown(self, rules: Iterable[Any]) -> Iterator[UnknownFieldError]:
        from fluxrules.domain.unified_rule import Rule
        from fluxrules.engine.infrastructure.global_rule_repository import normalize_rule

        for rule in rules:
            canonical = rule if isinstance(rule, Rule) else normalize_rule(rule)
            label = canonical.name or (str(canonical.id) if canonical.id is not None else None)
            for field in referenced_fields(getattr(canonical, "conditions", None)):
                if field not in self.fields and field not in self.parents:
                    yield UnknownFieldError.for_field(
                        field, self.name, sorted(self.known), rule=label
                    )


@functools.lru_cache(maxsize=256)
def schema_info(model: type) -> FactSchemaInfo:
    """Describe a model class as a :class:`FactSchemaInfo` (cached per class).

    Raises:
        TypeError: when *model* is not a supported model class.
    """
    kind = _model_kind(model)
    if kind is None:
        raise TypeError(
            "fact_schema must be a Pydantic model, dataclass, attrs class, msgspec "
            f"Struct or TypedDict class, got {model!r}"
        )
    leaves: dict[str, Any] = {}
    parents: set[str] = set()
    _describe(model, kind, "", leaves, parents, seen=(model,))
    return FactSchemaInfo(model=model, kind=kind, fields=leaves, parents=frozenset(parents))


def load_schema(spec: str, *, base_dir: str | Path | None = None) -> type:
    """Import a fact schema class named by an import string.

    Two forms, as used by ``fluxrules validate --schema`` and the
    ``fact_schema:`` key in rule files and ``fluxrules.yaml``:

    - ``"package.module:Class"`` imports the module. The current directory (and
      *base_dir*) are searched too, so a project's own modules work without
      installing the project.
    - ``"path/to/models.py:Class"`` loads the file directly. A relative path is
      resolved against *base_dir* (the directory of the file that names the
      schema), else the current directory.

    Importing runs the module's code, so only name schemas from trusted files.

    Raises:
        ImportError: when the string is malformed or the module, file or class
            cannot be found.
        TypeError: when the class is not a supported model class.
    """
    target, sep, attr = spec.rpartition(":")
    if not sep or not target or not attr:
        raise ImportError(
            f"fact schema {spec!r} must look like 'package.module:Class' or "
            "'path/to/models.py:Class'"
        )
    base = Path(base_dir) if base_dir is not None else Path.cwd()

    if target.endswith(".py") or "/" in target or "\\" in target:
        path = Path(target)
        if not path.is_absolute():
            path = base / path
        if not path.is_file():
            raise ImportError(f"fact schema file not found: {path}")
        module = _import_file(path)
    else:
        search = [p for p in dict.fromkeys((str(Path.cwd()), str(base))) if p not in sys.path]
        sys.path[:0] = search
        try:
            module = importlib.import_module(target)
        except ImportError as exc:
            raise ImportError(f"cannot import fact schema module {target!r}: {exc}") from exc
        finally:
            for entry in search:
                sys.path.remove(entry)

    model = getattr(module, attr, None)
    if model is None:
        raise ImportError(f"{target!r} has no class {attr!r}")
    schema_info(model)  # raises TypeError for an unsupported class
    return model


def _import_file(path: Path) -> types.ModuleType:
    """Import a Python file as a module, registered under a path-unique name."""
    path = path.resolve()
    name = f"_fluxrules_schema_{path.stem}_{abs(hash(str(path))):x}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load fact schema file {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before running: dataclasses and Pydantic resolve annotations
    # through sys.modules. The file's directory is importable for its siblings.
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    finally:
        sys.path.remove(str(path.parent))
    return module


def _describe(
    tp: type,
    kind: str,
    prefix: str,
    leaves: dict[str, Any],
    parents: set[str],
    seen: tuple[type, ...],
) -> None:
    for name, annotation in _field_types(tp, kind).items():
        path = f"{prefix}{name}"
        nested = _nested_model(annotation)
        # TypedDict values arrive as plain dicts and are not flattened.
        if nested is not None and kind != "typeddict" and nested not in seen:
            parents.add(path)
            _describe(nested, _model_kind(nested), f"{path}.", leaves, parents, (*seen, nested))  # type: ignore[arg-type]
        else:
            leaves[path] = annotation


def referenced_fields(conditions: Any) -> list[str]:
    """Every field a condition tree references, in tree order.

    Unlike the engine's typo scan this includes ``exists`` and ``accumulate``
    fields: a field the schema lacks is wrong whichever node names it.
    """
    out: list[str] = []
    _walk_fields(conditions, out)
    return list(dict.fromkeys(out))


def _walk_fields(node: Any, out: list[str]) -> None:
    if isinstance(node, list):
        for child in node:
            _walk_fields(child, out)
        return
    if not isinstance(node, dict):
        return
    field = node.get("field")
    if isinstance(field, str) and field:
        out.append(field)
    for key in ("condition", "child", "conditions", "children"):
        child = node.get(key)
        if child:
            _walk_fields(child, out)


# Checked field references


class _FieldRefs:
    """Attribute access over a schema that returns checked ``F`` references."""

    __slots__ = ("_info", "_prefix")

    def __init__(self, info: FactSchemaInfo, prefix: str) -> None:
        self._info = info
        self._prefix = prefix

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        from fluxrules.domain.field import F

        path = f"{self._prefix}{name}"
        if path in self._info.parents:
            return _FieldRefs(self._info, f"{path}.")
        self._info.check_field(path)
        return F(path)

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def __dir__(self) -> list[str]:
        return sorted(
            {
                path[len(self._prefix) :].split(".", 1)[0]
                for path in self._info.known
                if path.startswith(self._prefix)
            }
        )

    def __repr__(self) -> str:
        return f"fields({self._info.name}){'.' + self._prefix.rstrip('.') if self._prefix else ''}"


def fields(model: type) -> Any:
    """Checked field references for authoring rules against *model*.

    ``fields(Customer).age`` returns ``F("age")``, so every ``F`` operator works
    on it. Nested models chain: ``fields(Order).customer.age`` is
    ``F("customer.age")``. A field the model lacks raises
    :class:`~fluxrules.domain.errors.UnknownFieldError` at the point the rule is
    written, with a "did you mean" hint::

        from fluxrules import Rule
        from fluxrules.facts import fields

        c = fields(Customer)
        rule = Rule(name="adult", conditions=c.age >= 18, action="allow")
        c.agee  # UnknownFieldError: ... Did you mean 'age'?
    """
    return _FieldRefs(schema_info(model), "")


# Per-fact validation (engine intake)

VALIDATE_FACTS_MODES = ("off", "normalize", "strict")
ON_INVALID_MODES = ("raise", "skip", "quarantine")


@dataclass(frozen=True)
class QuarantinedFact:
    """A fact rejected by ``on_invalid="quarantine"``, with the reason."""

    facts: Any
    error: Any  # FactValidationError


class _FactIntake:
    """Validates and normalizes facts against an engine's ``fact_schema``.

    Built only when ``validate_facts`` is not ``"off"``, so engines without
    per-fact validation never touch it.
    """

    def __init__(
        self,
        info: FactSchemaInfo,
        validate_facts: str,
        on_invalid: str,
        quarantine_size: int = 1000,
    ) -> None:
        if info.kind in ("attrs", "msgspec"):
            raise TypeError(
                f"validate_facts={validate_facts!r} needs a schema Pydantic can validate "
                f"(a Pydantic model, dataclass or TypedDict); {info.name} is a "
                f"{info.kind} class. Use validate_facts='off' or a Pydantic model."
            )
        from collections import deque

        from pydantic import TypeAdapter

        self._info = info
        self._adapter: Any = TypeAdapter(info.model)
        self._strict = validate_facts == "strict"
        self._on_invalid = on_invalid
        self.quarantine: deque[QuarantinedFact] = deque(maxlen=quarantine_size)

    def admit(self, facts: Any) -> dict[str, Any] | None:
        """Return the validated flat fact dict, or ``None`` if it was rejected."""
        from pydantic import ValidationError

        from fluxrules.domain.errors import FactValidationError

        if isinstance(facts, self._info.model) and self._info.kind != "typeddict":
            return to_fact_dict(facts)  # already a validated instance
        if isinstance(facts, Mapping):
            raw = facts
        elif _instance_kind(facts) is not None:
            # Nested, not flattened: the schema validates nested models, and
            # the result is flattened below.
            raw = _plain(facts)
        else:
            raw = to_fact_dict(facts)
        try:
            validated = self._adapter.validate_python(raw, strict=self._strict)
        except ValidationError as exc:
            error = FactValidationError(self._info.name, exc.errors(include_url=False))
            if self._on_invalid == "raise":
                raise error from exc
            if self._on_invalid == "quarantine":
                self.quarantine.append(QuarantinedFact(facts=facts, error=error))
            else:
                logger.warning("Skipping invalid fact: %s", error)
            return None
        return to_fact_dict(validated)


# Pydantic alias generator


def lenient_aliases() -> Any:
    """A Pydantic alias generator that accepts several key styles per field.

    For a field named ``user_age`` the validator accepts ``user_age``,
    ``userAge``, ``UserAge``, ``user-age`` and ``userage``. Use it on the
    model you pass as ``fact_schema``, together with
    ``validate_facts="normalize"``, so the engine renames incoming keys to the
    field names your rules use::

        from pydantic import BaseModel, ConfigDict
        from fluxrules.facts import lenient_aliases

        class Customer(BaseModel):
            model_config = ConfigDict(alias_generator=lenient_aliases())
            user_age: int

        Customer.model_validate({"userAge": 30}).user_age  # 30

    The accepted spellings are listed per field rather than produced by
    rewriting every incoming key, so a key that is not a spelling of a declared
    field is never folded into one. If a payload carries two spellings of the
    same field, Pydantic takes the first one listed above. Output aliases are
    unchanged. Works with Pydantic 2.8 and later.
    """
    from pydantic import AliasChoices, AliasGenerator
    from pydantic.alias_generators import to_camel, to_pascal

    def _choices(name: str) -> AliasChoices:
        spellings = [
            name,
            to_camel(name),
            to_pascal(name),
            name.replace("_", "-"),
            name.replace("_", "").lower(),
        ]
        return AliasChoices(*dict.fromkeys(spellings))

    return AliasGenerator(validation_alias=_choices)
