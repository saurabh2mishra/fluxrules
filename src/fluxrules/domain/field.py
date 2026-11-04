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
    ``ends_with``, ``regex``, ``approx``, the ``_ignore_case`` methods and
    ``exists``).
    """

    def __init__(self, name: str) -> None:
        if not name or not isinstance(name, str):
            raise ValueError("Field name must be a non-empty string")
        self._name = name

    # __eq__ returns Condition, not bool - hashing would be meaningless.
    __hash__ = None  # type: ignore[assignment]

    def _cond(self, op: str, value: Any) -> Condition:
        node = {"type": "condition", "field": self._name, "op": op, "value": value}
        if op in ("in", "not_in", "in_ignore_case"):
            from fluxrules.domain.conditions.membership import normalize_membership_values

            node = normalize_membership_values(node, path="")
        return Condition(node)

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

    def approx(
        self,
        value: Any,
        *,
        abs_tol: float | None = None,
        rel_tol: float | None = None,
    ) -> Condition:
        """Field value is a number close to *value*, by ``math.isclose``.

        ``F("total").approx(0.3)`` matches ``0.1 + 0.2``. The default tolerance
        is ``rel_tol=1e-09`` and ``abs_tol=0``, so near zero give *abs_tol*:
        ``F("balance").approx(0, abs_tol=0.005)``. With a tolerance, the
        condition's value is ``{"value": value, "abs_tol": ..., "rel_tol": ...}``.
        """
        if abs_tol is None and rel_tol is None:
            return self._cond("approx", value)
        target: dict[str, Any] = {"value": value}
        if abs_tol is not None:
            target["abs_tol"] = abs_tol
        if rel_tol is not None:
            target["rel_tol"] = rel_tol
        return self._cond("approx", target)

    def equals_ignore_case(self, value: str) -> Condition:
        """Field value is the text *value*, ignoring case (``str.casefold``)."""
        return self._cond("equals_ignore_case", value)

    def in_ignore_case(self, values: Any) -> Condition:
        """Field value is one of the texts in *values*, ignoring case."""
        return self._cond("in_ignore_case", values)

    def contains_ignore_case(self, value: str) -> Condition:
        """Field text contains *value*, or a field list holds it, ignoring case."""
        return self._cond("contains_ignore_case", value)

    def starts_with_ignore_case(self, prefix: str) -> Condition:
        """Field text starts with *prefix*, ignoring case."""
        return self._cond("starts_with_ignore_case", prefix)

    def ends_with_ignore_case(self, suffix: str) -> Condition:
        """Field text ends with *suffix*, ignoring case."""
        return self._cond("ends_with_ignore_case", suffix)

    def exists(self) -> Condition:
        """Field is present in the fact map (EXISTS node)."""
        return Condition({"type": "exists", "field": self._name})

    def __repr__(self) -> str:
        return f"F({self._name!r})"


#: Short alias - the idiomatic way to use Field in rule expressions.
F = Field

__all__ = ["Condition", "F", "Field"]
