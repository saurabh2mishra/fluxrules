"""Dictionary utilities for fact transformation.

This module provides a configurable flattener with seven list-handling
strategies, cycle detection, and depth limiting, suitable for processing
complex nested data structures and untrusted input.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

__all__ = [
    "ListStrategy",
    "flatten_dict",
]


class ListStrategy(str, Enum):
    """How :func:`flatten_dict` should handle list values.

    Members:
        FIRST_ONLY: Flatten only the first dict item.
        ALL_WITH_INDEX: Flatten every dict item with an indexed key
            (``items[0].x``, ``items[1].x`` ...).
        MERGE_ALL: Merge all dict items into one (later items win).
        KEEP_AS_LIST: Keep the list value untouched under its key.
        COMMA_SEPARATED: Join scalar items with commas into a string.
        JSON_ENCODED: Encode the entire list as a JSON string.
        DROP: Drop list values entirely.
    """

    FIRST_ONLY = "first_only"
    ALL_WITH_INDEX = "all_with_index"
    MERGE_ALL = "merge_all"
    KEEP_AS_LIST = "keep_as_list"
    COMMA_SEPARATED = "comma_separated"
    JSON_ENCODED = "json_encoded"
    DROP = "drop"


def flatten_dict(
    data: dict[str, Any],
    parent_key: str = "",
    sep: str = ".",
    *,
    list_strategy: ListStrategy = ListStrategy.FIRST_ONLY,
    max_depth: int = 100,
    _depth: int = 0,
    _seen: frozenset[int] | None = None,
) -> dict[str, Any]:
    """Flatten a nested dictionary with configurable list handling.

    Unlike earlier versions, this now offers seven list strategies,
    detects cycles (preventing stack overflow on circular references), and
    enforces a configurable maximum recursion depth.

    Example:
        >>> flatten_dict({"user": {"age": 25}})
        {'user.age': 25}

    Args:
        data: The nested dictionary to flatten.
        parent_key: Prefix for recursion (internal use).
        sep: Separator between nested keys.
        list_strategy: How to handle list values. See :class:`ListStrategy`.
        max_depth: Maximum recursion depth before raising :class:`ValueError`.
        _depth: Current recursion depth (internal use).
        _seen: Object ids already visited, for cycle detection (internal use).

    Returns:
        A flat dictionary with dot-notation keys.

    Raises:
        ValueError: If ``max_depth`` is exceeded or a cycle is detected.
    """
    if _depth > max_depth:
        raise ValueError(f"flatten_dict exceeded max_depth={max_depth}")

    seen = _seen if _seen is not None else frozenset()
    if id(data) in seen:
        raise ValueError("flatten_dict detected a circular reference")
    seen = seen | {id(data)}

    items: list[tuple[str, Any]] = []
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(
                flatten_dict(
                    value,
                    new_key,
                    sep,
                    list_strategy=list_strategy,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen=seen,
                ).items()
            )
        elif isinstance(value, list):
            items.extend(
                _flatten_list(
                    value,
                    new_key,
                    sep,
                    list_strategy=list_strategy,
                    max_depth=max_depth,
                    depth=_depth,
                    seen=seen,
                )
            )
        else:
            items.append((new_key, value))
    return dict(items)


def _flatten_list(
    value: list[Any],
    new_key: str,
    sep: str,
    *,
    list_strategy: ListStrategy,
    max_depth: int,
    depth: int,
    seen: frozenset[int],
) -> list[tuple[str, Any]]:
    """Apply ``list_strategy`` to a list value, returning flattened items."""
    if list_strategy is ListStrategy.DROP:
        return []
    if list_strategy is ListStrategy.KEEP_AS_LIST:
        return [(new_key, value)]
    if list_strategy is ListStrategy.JSON_ENCODED:
        return [(new_key, json.dumps(value))]
    if list_strategy is ListStrategy.COMMA_SEPARATED:
        return [(new_key, ",".join(str(item) for item in value))]

    dict_items = [item for item in value if isinstance(item, dict)]

    if list_strategy is ListStrategy.FIRST_ONLY:
        if dict_items:
            return list(
                flatten_dict(
                    dict_items[0],
                    f"{new_key}[0]",
                    sep,
                    list_strategy=list_strategy,
                    max_depth=max_depth,
                    _depth=depth + 1,
                    _seen=seen,
                ).items()
            )
        return [(new_key, value)] if value else []

    if list_strategy is ListStrategy.ALL_WITH_INDEX:
        out: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            indexed_key = f"{new_key}[{index}]"
            if isinstance(item, dict):
                out.extend(
                    flatten_dict(
                        item,
                        indexed_key,
                        sep,
                        list_strategy=list_strategy,
                        max_depth=max_depth,
                        _depth=depth + 1,
                        _seen=seen,
                    ).items()
                )
            else:
                out.append((indexed_key, item))
        return out

    # MERGE_ALL
    merged: dict[str, Any] = {}
    for item in dict_items:
        merged.update(
            flatten_dict(
                item,
                new_key,
                sep,
                list_strategy=list_strategy,
                max_depth=max_depth,
                _depth=depth + 1,
                _seen=seen,
            )
        )
    return list(merged.items())
