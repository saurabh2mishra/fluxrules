"""Turn a single ``in`` / ``not_in`` value into a one-item list.

``{"op": "in", "value": "US"}`` means "is one of these values", so its value
should be a list. :func:`normalize_membership_values` rewrites such a value to
``["US"]`` and warns the author with :class:`MembershipValueWarning`, once, when
the rule is created. Every evaluation path then sees the same list.
"""

from __future__ import annotations

import os
import sys
import warnings
from types import FrameType
from typing import Any

from fluxrules.domain.errors import MembershipValueWarning
from fluxrules.engine.operators import MEMBERSHIP_OPS, is_membership_collection

__all__ = ["normalize_membership_values"]

_FLUXRULES_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PYDANTIC_MARKER = f"{os.sep}pydantic{os.sep}"


def _caller_stacklevel() -> int:
    """Stack level of the first frame outside fluxrules and pydantic.

    The warning then points at the line that wrote the rule, not at the
    validator that noticed the problem. The ``__init__`` that ``dataclasses``
    generates (file ``<string>``) is skipped too.
    """
    level = 1
    frame: FrameType | None = sys._getframe(1)
    while frame is not None:
        code = frame.f_code
        generated_init = code.co_filename == "<string>" and code.co_name == "__init__"
        filename = os.path.abspath(code.co_filename)
        if (
            not generated_init
            and not filename.startswith(_FLUXRULES_DIR)
            and _PYDANTIC_MARKER not in filename
        ):
            return level
        frame = frame.f_back
        level += 1
    return level


def _warn(path: str, node: dict[str, Any]) -> None:
    op = node["op"]
    value = node["value"]
    single = "==" if op == "in" else "!="
    warnings.warn(
        f"Condition{f' at {path!r}' if path else ''} on field {node.get('field')!r}: "
        f"'{op}' expects a list "
        f"of values, but got {value!r}. It is treated as [{value!r}]. Write "
        f"[{value!r}], or use '{single}' to compare a single value, to silence "
        "this warning.",
        MembershipValueWarning,
        stacklevel=_caller_stacklevel(),
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
            tree.get("op") in MEMBERSHIP_OPS
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
