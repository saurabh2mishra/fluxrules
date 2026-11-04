"""Turn a single ``in`` / ``not_in`` / ``in_ignore_case`` value into a one-item list.

``{"op": "in", "value": "US"}`` means "is one of these values", so its value
should be a list. :func:`normalize_membership_values` rewrites such a value to
``["US"]`` and warns the author with :class:`MembershipValueWarning`, once, when
the rule is created. Every evaluation path then sees the same list.
"""

from __future__ import annotations

import warnings
from typing import Any

from fluxrules.domain.errors import MembershipValueWarning
from fluxrules.engine.operators import MEMBERSHIP_OPS, is_membership_collection
from fluxrules.utils.warn import caller_stacklevel

__all__ = ["normalize_membership_values"]


# Operators whose value is a list of members.
_LIST_OPS = MEMBERSHIP_OPS | {"in_ignore_case"}
# The operator that compares one value, for each.
_SINGLE = {"in": "==", "not_in": "!=", "in_ignore_case": "equals_ignore_case"}


def _warn(path: str, node: dict[str, Any]) -> None:
    op = node["op"]
    value = node["value"]
    single = _SINGLE[op]
    warnings.warn(
        f"Condition{f' at {path!r}' if path else ''} on field {node.get('field')!r}: "
        f"'{op}' expects a list "
        f"of values, but got {value!r}. It is treated as [{value!r}]. Write "
        f"[{value!r}], or use '{single}' to compare a single value, to silence "
        "this warning.",
        MembershipValueWarning,
        stacklevel=caller_stacklevel(),
    )


def normalize_membership_values(tree: Any, *, path: str = "root", warn: bool = True) -> Any:
    """Return *tree* with every single ``in`` / ``not_in`` value wrapped in a list.

    The input is not modified. Nodes that need no change are returned as they
    are, so a tree without such values comes back unchanged. Malformed trees
    are passed through for the validator to report.
    """
    if isinstance(tree, list):
        changed = False
        items = []
        for i, item in enumerate(tree):
            new = normalize_membership_values(item, path=f"{path}[{i}]", warn=warn)
            changed = changed or new is not item
            items.append(new)
        return items if changed else tree
    if not isinstance(tree, dict):
        return tree

    if tree.get("type") == "condition":
        if (
            tree.get("op") in _LIST_OPS
            and "value" in tree
            and not is_membership_collection(tree["value"])
        ):
            if warn:
                _warn(path, tree)
            return {**tree, "value": [tree["value"]]}
        return tree

    out: dict[str, Any] | None = None
    for key, child in tree.items():
        if not isinstance(child, (dict, list)):
            continue
        new = normalize_membership_values(child, path=f"{path}.{key}", warn=warn)
        if new is not child:
            if out is None:
                out = dict(tree)
            out[key] = new
    return tree if out is None else out
