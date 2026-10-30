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
        types_ = {n: tp.model_fields[n].annotation for n in names}  # type: ignore[attr-defined]
        # Computed fields are in model_dump(), so rules may reference them.
        for n, computed in getattr(tp, "model_computed_fields", {}).items():
            types_[n] = computed.return_type
        return types_
    try:
        hints = typing.get_type_hints(tp)
    except Exception:  # unresolvable forward references: treat as untyped
        hints = {}
    return {n: hints.get(n, Any) for n in names}


def _nested_models(annotation: Any) -> tuple[list[type], bool]:
    """The model classes a field can hold, and whether it can hold a plain value.

    Unwraps ``Annotated`` and unions, so ``Optional[Annotated[Customer, ...]]``
    gives ``[Customer]`` and ``Person | Company`` gives both. ``None`` in a
    union is not a plain value: a ``None`` field stays a key either way.
    """
    if _model_kind(annotation) not in (None, "typeddict"):
        return [annotation], False
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _nested_models(typing.get_args(annotation)[0])
    if origin is typing.Union or origin is types.UnionType:
        models: list[type] = []
        plain = False
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            arg_models, arg_plain = _nested_models(arg)
            models.extend(m for m in arg_models if m not in models)
            plain = plain or arg_plain
        return models, plain
    return [], True


# Instance -> flat dict


_SCALARS = (str, int, float, bool, type(None))


def _plain(value: Any, *, computed: bool = True) -> Any:
    """Convert models nested inside containers to plain dicts (not flattened).

    With ``computed=False``, Pydantic computed fields are left out: they are
    derived output, and validation input must not carry them.
    """
    if isinstance(value, _SCALARS):
        return value
    kind = _instance_kind(value)
    if kind == "pydantic":
        if computed:
            return value.model_dump(by_alias=False)
        return _dump_without_computed(value)
    if kind is not None:
        return {
            n: _plain(getattr(value, n), computed=computed)
            for n in _instance_field_names(_cls(value), kind)
        }
    if isinstance(value, list):
        return [_plain(v, computed=computed) for v in value]
    if isinstance(value, tuple):
        return tuple(_plain(v, computed=computed) for v in value)
    if isinstance(value, dict):
        return {k: _plain(v, computed=computed) for k, v in value.items()}
    return value


def _dump_without_computed(model: Any) -> dict[str, Any]:
    """``model_dump`` without computed fields, at every nesting level when supported."""
    try:
        return model.model_dump(by_alias=False, exclude_computed_fields=True)
    except TypeError:
        # Pydantic before 2.12: leave out this model's own computed fields.
        computed = set(getattr(type(model), "model_computed_fields", {}))
        return model.model_dump(by_alias=False, exclude=computed or None)


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
        _flatten_pydantic(obj, obj.model_dump(by_alias=False), prefix, out)
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
        # by_alias=False: keys are field names, which rules use, even when the
        # model sets serialize_by_alias.
        dumped = facts.model_dump(by_alias=False)
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
        parents: dotted prefixes of nested models (``customer``). They are not
            fields: a nested model is flattened into its own fields, so a fact
            never has a ``customer`` key. A rule naming one is refused.
        open_paths: fields typed ``Any`` or ``object``. A model held there is
            flattened too, so any dotted path below one is accepted.
    """

    model: type
    kind: str
    fields: Mapping[str, Any]
    parents: frozenset[str]
    open_paths: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return self.model.__name__

    @property
    def known(self) -> frozenset[str]:
        """Every field path a rule may reference (leaves and parents)."""
        return frozenset(self.fields) | self.parents

    def check_field(self, field: str, *, rule: str | None = None) -> None:
        """Raise :class:`UnknownFieldError` unless a rule may reference *field*."""
        error = self._problem(field, rule)
        if error is not None:
            raise error

    def _problem(self, field: str, rule: str | None) -> UnknownFieldError | None:
        if field in self.fields:
            return None
        if any(field.startswith(f"{path}.") for path in self.open_paths):
            return None
        if field in self.parents:
            children = sorted(f for f in self.fields if f.startswith(f"{field}."))
            return UnknownFieldError.for_parent(field, self.name, children, rule=rule)
        return UnknownFieldError.for_field(field, self.name, sorted(self.known), rule=rule)

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
                error = self._problem(field, label)
                if error is not None:
                    yield error


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
    open_paths: set[str] = set()
    _describe(model, kind, "", leaves, parents, open_paths, seen=(model,))
    return FactSchemaInfo(
        model=model,
        kind=kind,
        fields=leaves,
        parents=frozenset(parents),
        open_paths=frozenset(open_paths),
    )


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
    open_paths: set[str],
    seen: tuple[type, ...],
) -> None:
    for name, annotation in _field_types(tp, kind).items():
        path = f"{prefix}{name}"
        # TypedDict values arrive as plain dicts and are not flattened.
        models, plain = _nested_models(annotation) if kind != "typeddict" else ([], True)
        models = [m for m in models if m not in seen]
        for nested in models:
            # Every model a union allows contributes its fields under the path.
            parents.add(path)
            _describe(
                nested,
                _model_kind(nested),  # type: ignore[arg-type]
                f"{path}.",
                leaves,
                parents,
                open_paths,
                (*seen, nested),
            )
        if plain or not models:
            leaves[path] = annotation
        if kind != "typeddict" and _is_open(annotation):
            open_paths.add(path)


def _is_open(annotation: Any) -> bool:
    """Whether a field may hold any value, so a model in it is flattened too."""
    if annotation is Any or annotation is object:
        return True
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _is_open(typing.get_args(annotation)[0])
    if origin is typing.Union or origin is types.UnionType:
        return any(_is_open(arg) for arg in typing.get_args(annotation))
    return False


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
    """Attribute access over a schema that returns checked ``F`` references.

    A nested model returns another ``_FieldRefs`` for its fields. It is not a
    field itself, so comparing it or calling ``.exists()`` on it raises with a
    hint, unless the path can also hold a plain value (``Person | str``), in
    which case it works like ``F(path)``.
    """

    __slots__ = ("_info", "_prefix", "_leaf")

    def __init__(self, info: FactSchemaInfo, prefix: str, leaf: bool = False) -> None:
        self._info = info
        self._prefix = prefix
        self._leaf = leaf

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        from fluxrules.domain.field import F

        path = f"{self._prefix}{name}"
        if path in self._info.parents:
            return _FieldRefs(self._info, f"{path}.", leaf=path in self._info.fields)
        if self._prefix and path not in self._info.fields and _is_field_member(name):
            # An F method such as exists() or isin() on this nested model.
            return getattr(self._as_field(), name)
        self._info.check_field(path)
        return F(path)

    def _as_field(self) -> Any:
        from fluxrules.domain.field import F

        own = self._prefix[:-1]
        if not own:
            raise TypeError(f"fields({self._info.name}) is not a field; use one of its fields")
        if not self._leaf:
            error = self._info._problem(own, None)
            assert error is not None  # a pure parent is never a field
            raise error
        return F(own)

    def __eq__(self, other: object) -> Any:  # type: ignore[override]
        return self._as_field() == other

    def __ne__(self, other: object) -> Any:  # type: ignore[override]
        return self._as_field() != other

    def __lt__(self, other: Any) -> Any:
        return self._as_field() < other

    def __le__(self, other: Any) -> Any:
        return self._as_field() <= other

    def __gt__(self, other: Any) -> Any:
        return self._as_field() > other

    def __ge__(self, other: Any) -> Any:
        return self._as_field() >= other

    __hash__ = object.__hash__

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


def _is_field_member(name: str) -> bool:
    """Whether *name* is a public method or attribute of ``F`` (such as ``exists``)."""
    from fluxrules.domain.field import F

    return not name.startswith("_") and hasattr(F, name)


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
        self._strict = validate_facts == "strict"
        # Strict mode only accepts dataclass instances, never dicts, so a schema
        # containing dataclasses is validated through a Pydantic stand-in.
        model = _strict_mirror(info.model) if self._strict else info.model
        self._adapter: Any = TypeAdapter(model)
        self._on_invalid = on_invalid
        self.quarantine: deque[QuarantinedFact] = deque(maxlen=quarantine_size)

    def admit(self, facts: Any) -> dict[str, Any] | None:
        """Return the validated flat fact dict, or ``None`` if it was rejected."""
        from pydantic import ValidationError

        from fluxrules.domain.errors import FactValidationError

        # TypedDict classes do not support isinstance, so check the kind first.
        if self._info.kind != "typeddict" and isinstance(facts, self._info.model):
            return to_fact_dict(facts)  # already a validated instance
        if isinstance(facts, Mapping):
            # Flat dotted keys (the engine's own shape, or Flatten output) are
            # nested again so the schema can validate them.
            raw = _nest_dotted(facts, self._info.parents)
        elif _instance_kind(facts) is not None:
            # Nested, not flattened: the schema validates nested models, and
            # the result is flattened below. Computed fields are output, not
            # input, so they are left out.
            raw = _plain(facts, computed=False)
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


def _nest_dotted(facts: Mapping[str, Any], parents: frozenset[str]) -> Mapping[str, Any]:
    """Turn flat dotted keys into nested dicts where the path is a nested model.

    ``{"customer.age": 30}`` becomes ``{"customer": {"age": 30}}`` when
    ``customer`` is a nested model in the schema. Other keys are left as they
    are. Returns *facts* itself when there is nothing to nest.
    """
    if not parents or not any(isinstance(k, str) and "." in k for k in facts):
        return facts
    out: dict[str, Any] = {}
    for key, value in facts.items():
        if isinstance(key, str) and "." in key and key.split(".", 1)[0] in parents:
            node = out
            *heads, leaf = key.split(".")
            for head in heads:
                child = node.get(head)
                if not isinstance(child, dict):
                    child = node[head] = dict(child) if isinstance(child, Mapping) else {}
                node = child
            node[leaf] = value
        elif isinstance(out.get(key), dict) and isinstance(value, Mapping):
            out[key] = {**value, **out[key]}  # dotted keys win over a nested copy
        else:
            out[key] = value
    return out


# Finished mirrors by class, and classes being mirrored right now (so a
# self-referencing dataclass stops recursing instead of looping).
_MIRRORS: dict[type, type] = {}
_MIRRORING: set[type] = set()


def _strict_mirror(model: type) -> type:
    """A Pydantic model to validate *model* in strict mode, if it needs one.

    Pydantic's strict mode accepts only dataclass instances, never dicts, for a
    dataclass, so a fact dict could never pass. This builds a Pydantic model
    with the same fields, types and defaults, mirroring nested dataclasses too.
    Models without dataclasses are returned unchanged.
    """
    cached = _MIRRORS.get(model)
    if cached is not None:
        return cached
    if model in _MIRRORING or not _has_dataclass(model):
        return model
    mirror = _build_mirror(model)
    _MIRRORS[model] = mirror
    return mirror


def _build_mirror(model: type) -> type:
    from pydantic import Field as PydanticField
    from pydantic import create_model

    kind = _model_kind(model)
    _MIRRORING.add(model)
    try:
        if kind == "dataclass":
            hints = typing.get_type_hints(model, include_extras=True)
            definitions: dict[str, Any] = {}
            for f in dataclasses.fields(model):
                annotation = _mirror_annotation(hints.get(f.name, Any))
                if f.default is not dataclasses.MISSING:
                    definitions[f.name] = (annotation, f.default)
                elif f.default_factory is not dataclasses.MISSING:
                    definitions[f.name] = (
                        annotation,
                        PydanticField(default_factory=f.default_factory),
                    )
                else:
                    definitions[f.name] = (annotation, ...)
            return create_model(model.__name__, **definitions)  # type: ignore[call-overload,no-any-return]
        if kind == "pydantic":
            overrides = {
                name: (_mirror_annotation(info.annotation), info)
                for name, info in model.model_fields.items()  # type: ignore[attr-defined]
                if _has_dataclass(info.annotation)
            }
            if overrides:
                return create_model(model.__name__, __base__=model, **overrides)  # type: ignore[call-overload,no-any-return]
        return model
    finally:
        _MIRRORING.discard(model)


def _has_dataclass(annotation: Any, seen: frozenset[Any] = frozenset()) -> bool:
    """Whether a type is, or contains, a dataclass (through fields and type arguments)."""
    if annotation in seen:
        return False
    kind = _model_kind(annotation)
    if kind == "dataclass":
        return True
    if kind == "pydantic":
        seen = seen | {annotation}
        return any(
            _has_dataclass(info.annotation, seen) for info in annotation.model_fields.values()
        )
    return any(_has_dataclass(arg, seen) for arg in typing.get_args(annotation))


def _mirror_annotation(annotation: Any) -> Any:
    """*annotation* with every dataclass replaced by its strict mirror."""
    if _model_kind(annotation) in ("dataclass", "pydantic"):
        return _strict_mirror(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if not args or origin is typing.Literal:
        return annotation
    if origin is typing.Annotated:
        return typing.Annotated[(_mirror_annotation(args[0]), *args[1:])]  # type: ignore[valid-type]
    mirrored = tuple(_mirror_annotation(arg) for arg in args)
    if mirrored == args:
        return annotation
    if origin is typing.Union or origin is types.UnionType:
        return typing.Union[mirrored]  # noqa: UP007
    try:
        return origin[mirrored]  # type: ignore[index]
    except TypeError:
        return annotation


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
