"""Strict DSL validation for condition trees.

Validates DSL dictionaries before they are parsed or loaded into engines,
catching typos, invalid operators, and unknown keys early with clear errors.
"""

from __future__ import annotations

from typing import Any

from fluxrules.domain.errors import DSLValidationError
from fluxrules.engine.operators import VALID_OPERATORS

__all__ = ["DSLValidationError", "validate_dsl"]

# Valid keys for each DSL node type
_CONDITION_KEYS = {"type", "field", "op", "value"}
_GROUP_KEYS = {"type", "op", "children", "conditions"}
_NOT_KEYS = {"type", "condition", "children"}
_EXISTS_KEYS = {"type", "field"}
_SEQUENCE_KEYS = {"type", "steps", "within_seconds"}
_ACCUMULATE_KEYS = {"type", "field", "function", "source", "condition"}

_VALID_GROUP_OPS = {"AND", "OR", "and", "or"}
_VALID_ACCUMULATE_FUNCS = {"sum", "avg", "min", "max", "count"}


# ``DSLValidationError`` is defined once, in ``fluxrules.domain.errors``, and
# re-exported here for callers who import it from the module that raises it.
# It used to be *redefined* at this location: two distinct classes sharing a
# name and a code but not a base class, so `except errors.DSLValidationError`
# silently failed to catch what this module actually raised.


def validate_dsl(dsl: dict[str, Any], *, path: str = "root") -> None:
    """Validate a DSL dictionary recursively.

    Args:
        dsl: The DSL dict to validate.
        path: Dot-separated path for error context (e.g., "root.children[0]").

    Raises:
        DSLValidationError: If the DSL is invalid.
    """
    if not isinstance(dsl, dict):
        raise DSLValidationError(f"DSL node at '{path}' must be a dict, got {type(dsl).__name__}")

    node_type = dsl.get("type")
    if node_type is None:
        raise DSLValidationError(
            f"DSL node at '{path}' missing required 'type' key. "
            f"Valid types: condition, group, not, exists, sequence, accumulate"
        )

    if node_type == "condition":
        _validate_condition(dsl, path)
    elif node_type in ("group", "composite", "and", "or"):
        _validate_group(dsl, path)
    elif node_type == "not":
        _validate_not(dsl, path)
    elif node_type == "exists":
        _validate_exists(dsl, path)
    elif node_type == "sequence":
        _validate_sequence(dsl, path)
    elif node_type == "accumulate":
        _validate_accumulate(dsl, path)
    else:
        raise DSLValidationError(
            f"Unknown DSL node type '{node_type}' at '{path}'. "
            f"Valid types: condition, group, not, exists, sequence, accumulate"
        )


def _check_extra_keys(dsl: dict[str, Any], valid_keys: set, node_type: str, path: str) -> None:
    """Check for unknown keys in a DSL node."""
    extra = set(dsl.keys()) - valid_keys
    if extra:
        raise DSLValidationError(
            f"Unknown keys {sorted(extra)} in '{node_type}' node at '{path}'. "
            f"Valid keys: {sorted(valid_keys)}"
        )


def _validate_condition(dsl: dict[str, Any], path: str) -> None:
    _check_extra_keys(dsl, _CONDITION_KEYS, "condition", path)

    if "field" not in dsl:
        raise DSLValidationError(f"Condition at '{path}' missing required 'field' key")
    if not isinstance(dsl["field"], str) or not dsl["field"].strip():
        raise DSLValidationError(
            f"Condition at '{path}' has invalid 'field': must be a non-empty string"
        )

    if "op" not in dsl:
        raise DSLValidationError(f"Condition at '{path}' missing required 'op' key")
    if dsl["op"] not in VALID_OPERATORS:
        raise DSLValidationError(
            f"Invalid operator '{dsl['op']}' at '{path}'. "
            f"Valid operators: {sorted(VALID_OPERATORS)}"
        )

    if "value" not in dsl:
        raise DSLValidationError(f"Condition at '{path}' missing required 'value' key")


def _validate_group(dsl: dict[str, Any], path: str) -> None:
    node_type = dsl.get("type")
    _check_extra_keys(dsl, _GROUP_KEYS, node_type or "group", path)

    # ``and``/``or`` carry the boolean operator in the *type*; ``group``/
    # ``composite`` carry it in ``op``. Requiring ``op`` unconditionally
    # rejected the shape the engines actually evaluate.
    if node_type in ("group", "composite"):
        if "op" not in dsl:
            raise DSLValidationError(f"Group at '{path}' missing required 'op' key")
        if dsl["op"] not in _VALID_GROUP_OPS:
            raise DSLValidationError(
                f"Invalid group operator '{dsl['op']}' at '{path}'. Valid: AND, OR"
            )

    # Children live under "children" or, for the composite authoring shape,
    # "conditions".
    key = "children" if "children" in dsl else "conditions"
    children = dsl.get(key)
    if children is None:
        raise DSLValidationError(f"Group at '{path}' missing required 'children' key")
    if not isinstance(children, list):
        raise DSLValidationError(f"Group '{key}' at '{path}' must be a list")
    if len(children) == 0:
        raise DSLValidationError(f"Group at '{path}' has empty '{key}' list")

    for i, child in enumerate(children):
        validate_dsl(child, path=f"{path}.{key}[{i}]")


def _validate_not(dsl: dict[str, Any], path: str) -> None:
    _check_extra_keys(dsl, _NOT_KEYS, "not", path)

    # The strict authoring shape spells the child "condition"; the engine shape
    # uses "children". Accepting only the former rejected engine-produced trees.
    if "condition" in dsl:
        validate_dsl(dsl["condition"], path=f"{path}.condition")
        return

    children = dsl.get("children")
    if not children:
        raise DSLValidationError(f"NOT node at '{path}' missing required 'condition' key")
    for i, child in enumerate(children):
        validate_dsl(child, path=f"{path}.children[{i}]")


def _validate_exists(dsl: dict[str, Any], path: str) -> None:
    _check_extra_keys(dsl, _EXISTS_KEYS, "exists", path)

    if "field" not in dsl:
        raise DSLValidationError(f"EXISTS node at '{path}' missing required 'field' key")
    if not isinstance(dsl["field"], str) or not dsl["field"].strip():
        raise DSLValidationError(
            f"EXISTS node at '{path}' has invalid 'field': must be a non-empty string"
        )


def _validate_sequence(dsl: dict[str, Any], path: str) -> None:
    _check_extra_keys(dsl, _SEQUENCE_KEYS, "sequence", path)

    if "steps" not in dsl:
        raise DSLValidationError(f"SEQUENCE node at '{path}' missing required 'steps' key")
    if not isinstance(dsl["steps"], list) or len(dsl["steps"]) == 0:
        raise DSLValidationError(f"SEQUENCE 'steps' at '{path}' must be a non-empty list")
    for i, step in enumerate(dsl["steps"]):
        validate_dsl(step, path=f"{path}.steps[{i}]")


def _validate_accumulate(dsl: dict[str, Any], path: str) -> None:
    _check_extra_keys(dsl, _ACCUMULATE_KEYS, "accumulate", path)

    if "function" not in dsl:
        raise DSLValidationError(f"ACCUMULATE node at '{path}' missing required 'function' key")
    if dsl["function"] not in _VALID_ACCUMULATE_FUNCS:
        raise DSLValidationError(
            f"Invalid accumulate function '{dsl['function']}' at '{path}'. "
            f"Valid: {sorted(_VALID_ACCUMULATE_FUNCS)}"
        )
