"""Shared builders for API test payloads.

These helpers remove repeated inline rule definitions from the API tests so
each test states only the fields it cares about.
"""

from __future__ import annotations

from typing import Any


def build_rule_payload(
    name: str = "TestRule",
    *,
    action: str = "act",
    field: str = "x",
    op: str = "==",
    value: Any = 1,
    condition_dsl: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a payload for the ``POST /api/v1/rules`` endpoint.

    A minimal single-condition rule is produced by default. Pass
    ``condition_dsl`` to supply a full condition tree, or set ``field``,
    ``op``, and ``value`` to shape the default condition. Additional rule
    fields such as ``group``, ``priority``, ``description``, or ``enabled``
    can be provided as keyword arguments.
    """
    if condition_dsl is None:
        condition_dsl = {"type": "condition", "field": field, "op": op, "value": value}
    payload: dict[str, Any] = {
        "name": name,
        "condition_dsl": condition_dsl,
        "action": action,
    }
    payload.update(extra)
    return payload
