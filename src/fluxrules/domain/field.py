"""Fluent condition authoring via operator overloading.

Build conditions with natural Python operators::

    from fluxrules import F, Rule

    rule = Rule(
        name="high-value-us",
        conditions=(F("amount") > 10000) & (F("country") == "US"),
        action="flag",
    )

**Operator precedence warning**: Python's ``&`` and ``|`` bind more tightly
than comparisons like ``>``, ``<``, ``==``. Always parenthesise each
individual condition when composing them::

    # Correct
    (F("amount") > 10000) & (F("country") == "US")

    # Wrong - ``&`` binds before ``==``, producing a TypeError at runtime
    F("amount") > 10000 & F("country") == "US"

Each expression produces the same condition dict the engine already accepts, so
the engine, validator, and persistence layer see no difference.

Operator mapping
----------------
- ``F("x") > v``       → ``{"type":"condition","field":"x","op":">","value":v}``
- ``a & b``             → ``{"type":"group","op":"AND","children":[a,b]}``
- ``a | b``             → ``{"type":"group","op":"OR","children":[a,b]}``
- ``~a``                → ``{"type":"not","condition":a}``
- ``F("x").isin([…])`` → ``{"type":"condition","field":"x","op":"in","value":[…]}``
- ``F("x").exists()``   → ``{"type":"exists","field":"x"}``
"""

from __future__ import annotations

from typing import Any


class Condition:
    """A wrapped condition dict with Python boolean operators for composition.

    Produced by :class:`Field` operator expressions. Pass directly to
    ``Rule(conditions=...)``; the Rule validator unwraps it automatically.
    """

    def __init__(self, dict_: dict[str, Any]) -> None:
        self._dict = dict_

    def to_dict(self) -> dict[str, Any]:
        """Return the underlying condition dict."""
        return self._dict

    def __and__(self, other: Condition) -> Condition:
        right = other._dict if isinstance(other, Condition) else other
        return Condition({"type": "group", "op": "AND", "children": [self._dict, right]})

    def __or__(self, other: Condition) -> Condition:
        right = other._dict if isinstance(other, Condition) else other
        return Condition({"type": "group", "op": "OR", "children": [self._dict, right]})

    def __invert__(self) -> Condition:
        return Condition({"type": "not", "condition": self._dict})

    def __repr__(self) -> str:
        return f"Condition({self._dict!r})"


class Field:
    """A field reference that produces :class:`Condition` objects via Python operators.

    Use the short alias ``F`` in practice::

        from fluxrules import F

        cond = (F("amount") > 10000) & (F("country") == "US")

    All operators accepted by ``VALID_OPERATORS`` are available either as Python
    dunder methods (``>``, ``>=``, ``<``, ``<=``, ``==``, ``!=``) or as named
    methods (``isin``, ``not_in``, ``contains``, ``not_contains``, ``starts_with``,
    ``ends_with``, ``regex``, ``exists``).
    """

    def __init__(self, name: str) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("Field name must be a non-empty string")
        self._name = name

    # __eq__ returns Condition, not bool - hashing would be meaningless.
    __hash__ = None  # type: ignore[assignment]

    def _cond(self, op: str, value: Any) -> Condition:
        return Condition({"type": "condition", "field": self._name, "op": op, "value": value})

    # --- comparison operators -------------------------------------------------

    def __gt__(self, value: Any) -> Condition:
        return self._cond(">", value)

    def __ge__(self, value: Any) -> Condition:
        return self._cond(">=", value)

    def __lt__(self, value: Any) -> Condition:
        return self._cond("<", value)

    def __le__(self, value: Any) -> Condition:
        return self._cond("<=", value)

    def __eq__(self, value: Any) -> Condition:  # type: ignore[override]
        return self._cond("==", value)

    def __ne__(self, value: Any) -> Condition:  # type: ignore[override]
        return self._cond("!=", value)

    # --- named operators for types Python cannot express as dunders -----------

    def isin(self, values: Any) -> Condition:
        """Field value is a member of *values*."""
        return self._cond("in", values)

    def not_in(self, values: Any) -> Condition:
        """Field value is not a member of *values*."""
        return self._cond("not_in", values)

    def contains(self, value: Any) -> Condition:
        """Field value (string or collection) contains *value*."""
        return self._cond("contains", value)

    def not_contains(self, value: Any) -> Condition:
        """Field value does not contain *value*."""
        return self._cond("not_contains", value)

    def starts_with(self, prefix: str) -> Condition:
        """Field value starts with *prefix*."""
        return self._cond("starts_with", prefix)

    def ends_with(self, suffix: str) -> Condition:
        """Field value ends with *suffix*."""
        return self._cond("ends_with", suffix)

    def regex(self, pattern: str) -> Condition:
        """Field value matches regular expression *pattern*."""
        return self._cond("regex", pattern)

    def exists(self) -> Condition:
        """Field is present in the fact map (EXISTS node)."""
        return Condition({"type": "exists", "field": self._name})

    def __repr__(self) -> str:
        return f"F({self._name!r})"


#: Short alias - the idiomatic way to use Field in rule expressions.
F = Field

__all__ = ["Condition", "F", "Field"]
