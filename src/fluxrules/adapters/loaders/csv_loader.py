"""CSV decision table loader - load rules from a CSV file.

CSV supports **two styles**:

**Style 1: Simple (single-condition rules)**
    id, name, priority, fact, operator, value, action, enabled

Each row becomes one single-condition rule.

Example::

    id,name,priority,fact,operator,value,action,enabled
    1,high_value,10,amount,>,1000,flag_for_review,true
    2,young_user,20,age,<,25,require_verification,true

**Style 2: DSL (any complexity - single or multi-condition)**
    id, name, priority, condition_dsl, action, enabled

The ``condition_dsl`` column contains a JSON condition object.
This style supports single conditions, AND groups, OR groups, and composites.

Example::

    id,name,priority,condition_dsl,action,enabled
    1,high_value,10,"{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":1000}",flag_for_review,true
    2,young_and_rich,20,"{""type"":""group"",""op"":""AND"",""children"":[{""type"":""condition"",""field"":""age"",""op"":""<"",""value"":25},{""type"":""condition"",""field"":""amount"",""op"":"">"",""value"":500}]}",escalate,true
    3,young_or_poor,15,"{""type"":""group"",""op"":""OR"",""children"":[{""type"":""condition"",""field"":""age"",""op"":""<"",""value"":18},{""type"":""condition"",""field"":""balance"",""op"":""<"",""value"":100}]}",review,true

For readability with complex conditions, use a tool like `jq` to format JSON:
    jq -c '{type:"group",op:"AND",children:[...]}' | sed 's/"/\\"/g'
"""

from __future__ import annotations

import csv
import json
from typing import Any


def load_rules_from_csv(path: str) -> list[dict[str, Any]]:
    """Load rules from a CSV decision table.

    Supports two CSV styles:
    - **Simple**: columns (id, name, priority, fact, operator, value, action, enabled)
    - **DSL**: columns (id, name, priority, condition_dsl, action, enabled)

    Args:
        path: Path to the CSV file.

    Returns:
        A list of rule dicts ready to pass to ``RuleEngine.add_rules()``.

    Raises:
        ValueError: If required columns are missing or condition_dsl is invalid JSON.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []

        headers = {h.strip().lower() for h in reader.fieldnames}

        # Detect style
        has_dsl_col = "condition_dsl" in headers
        has_simple_cols = {"fact", "operator", "value"} <= headers

        if has_dsl_col:
            return _load_dsl_style(reader, headers)
        elif has_simple_cols:
            return _load_simple_style(reader, headers)
        else:
            raise ValueError(
                f"CSV must have either:\n"
                f"  - DSL style: (id, name, priority, condition_dsl, action, enabled)\n"
                f"  - Simple style: (id, name, priority, fact, operator, value, action, enabled)\n"
                f"Found columns: {sorted(headers)}"
            )


def _load_simple_style(reader: Any, headers: set[str]) -> list[dict[str, Any]]:
    """Load Simple style CSV (one condition per row, same id groups them as AND)."""
    required = {"id", "name", "priority", "fact", "operator", "value", "action"}
    missing = required - headers
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    groups: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}

    for row in reader:
        rid = str(row["id"]).strip()
        fact = row["fact"].strip()
        operator = row["operator"].strip()
        value_raw = row["value"].strip()

        # Try to coerce value to a number
        try:
            value: Any = int(value_raw)
        except ValueError:
            try:
                value = float(value_raw)
            except ValueError:
                value = value_raw

        condition = {
            "type": "condition",
            "field": fact,
            "op": operator,
            "value": value,
        }

        groups.setdefault(rid, []).append(condition)
        if rid not in meta:
            meta[rid] = {
                "id": int(rid) if rid.isdigit() else rid,
                "name": row["name"].strip(),
                "priority": int(row.get("priority", 0) or 0),
                "action": row["action"].strip(),
                "enabled": str(row.get("enabled", "true")).strip().lower() != "false",
            }

    rules: list[dict[str, Any]] = []
    for rid, conditions in groups.items():
        m = meta[rid]
        if len(conditions) == 1:
            condition_dsl = conditions[0]
        else:
            condition_dsl = {"type": "group", "op": "AND", "children": conditions}
        rules.append(
            {
                "id": m["id"],
                "name": m["name"],
                "priority": m["priority"],
                "action": m["action"],
                "enabled": m["enabled"],
                "condition_dsl": condition_dsl,
            }
        )

    return rules


def _load_dsl_style(reader: Any, headers: set[str]) -> list[dict[str, Any]]:
    """Load DSL style CSV (condition_dsl column with inline JSON)."""
    required = {"id", "name", "priority", "condition_dsl", "action"}
    missing = required - headers
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    rules: list[dict[str, Any]] = []

    for row in reader:
        rid = str(row["id"]).strip()
        name = row["name"].strip()
        priority = int(row.get("priority", 0) or 0)
        action = row["action"].strip()
        enabled = str(row.get("enabled", "true")).strip().lower() != "false"
        condition_dsl_str = row["condition_dsl"].strip()

        # Handle single-quoted or double-quoted JSON in CSV
        if condition_dsl_str.startswith("'") and condition_dsl_str.endswith("'"):
            condition_dsl_str = condition_dsl_str[1:-1]
        elif condition_dsl_str.startswith('"') and condition_dsl_str.endswith('"'):
            condition_dsl_str = condition_dsl_str[1:-1]

        # Parse JSON from condition_dsl column
        try:
            condition_dsl = json.loads(condition_dsl_str)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Row id={rid} (name={name}): condition_dsl is not valid JSON: {e}"
            ) from e

        rules.append(
            {
                "id": int(rid) if rid.isdigit() else rid,
                "name": name,
                "priority": priority,
                "action": action,
                "enabled": enabled,
                "condition_dsl": condition_dsl,
            }
        )

    return rules
