"""Check rule values against the types of their fields in a fact schema.

With ``fact_schema=``, a rule comparing ``amount: float`` with the text
``"100.1"`` can never match, so :func:`check_tree` reports it as a
:class:`~fluxrules.domain.errors.RuleValueError` that suggests writing
``100.1``. An ISO date string compared with a ``date`` or ``datetime`` field
is converted to a date, because JSON rule files have no other way to write
one. Fields whose type is unclear (a union, ``Any``, an enum, ``Literal``, a
list) are not checked.
"""

from __future__ import annotations

import datetime as dt
import types
import typing
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from fluxrules.domain.conditions.rule_values import describe_value
from fluxrules.domain.errors import RuleValueError
from fluxrules.engine.operators import MEMBERSHIP_OPS, ORDERING_OPS

__all__ = ["check_tree", "field_kind"]

_COMPARE_OPS = ORDERING_OPS | {"==", "!="}
_ALIASES = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_TEXT_OPS = frozenset({"starts_with", "ends_with", "regex"})
_CONTAINS_OPS = frozenset({"contains", "not_contains"})

# A field's kind and the type name shown in messages.
Kind = tuple[str, str]


def field_kind(annotation: Any) -> Kind | None:
    """``("number", "float")``, ``("text", "str")`` and so on, or ``None``.

    ``Optional[X]`` and ``Annotated[X, ...]`` count as ``X``. Anything else
    that is not one plain type is ``None``: such a field is not checked.
    """
    while True:
        origin = typing.get_origin(annotation)
        if origin is typing.Annotated:
            annotation = typing.get_args(annotation)[0]
            continue
        if origin is typing.Union or origin is types.UnionType:
            others = [a for a in typing.get_args(annotation) if a is not type(None)]
            if len(others) != 1:
                return None
            annotation = others[0]
            continue
        break
    if annotation is bool:
        return ("bool", "bool")
    if annotation in (int, float, Decimal):
        return ("number", annotation.__name__)
    if annotation is str:
        return ("text", "str")
    if annotation is dt.datetime:
        return ("datetime", "datetime")
    if annotation is dt.date:
        return ("date", "date")
    return None


def check_tree(
    tree: Any,
    fields: typing.Mapping[str, Any],
    *,
    schema_name: str,
    rule: str | None,
    coerce_bool_strings: bool = False,
) -> tuple[Any, list[RuleValueError]]:
    """Check *tree* against the field types in *fields*.

    Returns the tree with ISO date strings converted (the same object when
    nothing changed), and every problem found, in tree order.
    """
    errors: list[RuleValueError] = []

    def visit(node: Any) -> Any:
        if isinstance(node, list):
            items = [visit(item) for item in node]
            return items if any(a is not b for a, b in zip(items, node, strict=True)) else node
        if not isinstance(node, dict):
            return node
        if node.get("type") == "condition":
            return _check_condition(
                node, fields, schema_name, rule, coerce_bool_strings, errors.append
            )
        out: dict[str, Any] | None = None
        for key, child in node.items():
            if not isinstance(child, (dict, list)):
                continue
            new = visit(child)
            if new is not child:
                if out is None:
                    out = dict(node)
                out[key] = new
        return node if out is None else out

    return visit(tree), errors


def _check_condition(
    node: dict[str, Any],
    fields: typing.Mapping[str, Any],
    schema_name: str,
    rule: str | None,
    coerce_bool_strings: bool,
    report: Callable[[RuleValueError], None],
) -> dict[str, Any]:
    field = node.get("field")
    op = node.get("op")
    if not isinstance(field, str) or not isinstance(op, str) or "value" not in node:
        return node
    if field not in fields:
        return node  # an unknown field is reported on its own
    kind = field_kind(fields[field])
    if kind is None:
        return node
    op = _ALIASES.get(op, op)
    value = node["value"]

    def problem(text: str, fix: str = "") -> None:
        where = f"Rule '{rule}': field" if rule else "Field"
        summary = (
            f"{where} '{field}' is {kind[1]} in {schema_name}, but {text}."
            f"{' ' + fix if fix else ''}"
        )
        report(
            RuleValueError(summary, field=field, rule=rule, schema_name=schema_name, value=value)
        )

    if op in _TEXT_OPS:
        if kind[0] != "text":
            problem(f"'{op}' tests text", "Compare it with '==' or an ordering operator instead.")
        return node
    if op in _CONTAINS_OPS:
        if kind[0] != "text":
            problem(f"'{op}' needs text or a collection to look in")
        elif not isinstance(value, str):
            problem(f"the rule looks for {describe_value(value)} in it", "Write the value as text.")
        return node
    if op in MEMBERSHIP_OPS and isinstance(value, (list, tuple, set, frozenset)):
        members = []
        changed = False
        for member in value:
            new = _check_value(kind, member, op, coerce_bool_strings, problem)
            changed = changed or new is not member
            members.append(new)
        if not changed:
            return node
        return {**node, "value": type(value)(members) if not isinstance(value, list) else members}
    if op in _COMPARE_OPS:
        new = _check_value(kind, value, op, coerce_bool_strings, problem)
        return node if new is value else {**node, "value": new}
    return node


def _check_value(
    kind: Kind,
    value: Any,
    op: str,
    coerce_bool_strings: bool,
    problem: Callable[..., None],
) -> Any:
    """*value*, converted when it is an ISO date for a date field.

    Calls *problem* when the value does not fit the field's kind.
    """
    if value is None:
        return value
    name = kind[0]
    compares = f"the rule compares it with {describe_value(value)}"
    if name == "number":
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and _is_number_text(value):
            problem(compares, f"Write {value.strip()} without quotes to compare numbers.")
        else:
            problem(compares, "Write a number.")
        return value
    if name == "text":
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            problem(compares, f'Write "{value}" in quotes to compare text.')
        else:
            problem(compares, "Write text.")
        return value
    if name == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            if coerce_bool_strings:
                return value
            problem(compares, f"Write {value.lower()} without quotes.")
        else:
            problem(compares, "Write true or false.")
        return value
    if name == "date":
        if isinstance(value, dt.datetime):
            problem(compares, "A date and a datetime cannot be compared; write the date only.")
            return value
        if isinstance(value, dt.date):
            return value
        if isinstance(value, str):
            parsed = _iso_date(value)
            if parsed is not None:
                return parsed
            if _iso_datetime(value) is not None:
                problem(compares, f"Write the date only, such as {value[:10]}.")
            else:
                problem(compares, "Write an ISO date such as 2024-05-01.")
            return value
        problem(compares, "Write an ISO date such as 2024-05-01.")
        return value
    # datetime
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        problem(compares, "A date and a datetime cannot be compared; write a date and time.")
        return value
    if isinstance(value, str):
        if _iso_date(value) is not None:
            problem(compares, f"Write a date and time, such as {value}T00:00:00.")
            return value
        parsed = _iso_datetime(value)
        if parsed is not None:
            return parsed
    problem(compares, "Write an ISO date and time such as 2024-05-01T09:30:00.")
    return value


def _is_number_text(value: str) -> bool:
    try:
        Decimal(value.strip())
    except InvalidOperation:
        return False
    return value.strip().lower() not in ("nan", "inf", "-inf", "+inf", "infinity", "snan")


def _iso_date(value: str) -> dt.date | None:
    """*value* as a date, when it is exactly ``YYYY-MM-DD``."""
    if len(value) != 10:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _iso_datetime(value: str) -> dt.datetime | None:
    """*value* as a datetime, when it is an ISO date with a time."""
    if len(value) <= 10:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None
