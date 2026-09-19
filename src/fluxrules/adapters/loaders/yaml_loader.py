"""YAML rule loader - load rules from a YAML file.

YAML schema: a list of rule mappings (or a single mapping) with the same
schema as the JSON/dict format used by ``RuleEngine.add_rules()``.

Requires: ``pip install pyyaml``

Example YAML::

    - id: 1
      name: high_value
      priority: 10
      action: flag_for_review
      enabled: true
      condition_dsl:
        type: condition
        field: amount
        op: ">"
        value: 1000
"""

from __future__ import annotations

from typing import Any


def load_rules_from_yaml(path: str) -> list[dict[str, Any]]:
    """Load rules from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        A list of rule dicts ready to pass to ``RuleEngine.add_rules()``.

    Raises:
        ImportError: When ``pyyaml`` is not installed.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "pyyaml is required for YAML rule loading. Install it with: pip install pyyaml"
        ) from exc
    with open(path) as f:
        rules = yaml.safe_load(f)
    return rules if isinstance(rules, list) else [rules]
