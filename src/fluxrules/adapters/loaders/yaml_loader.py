"""YAML rule loader - load rules from a YAML file.

YAML schema: a list of rule mappings (or a single mapping) with the same
schema as the JSON/dict format used by ``RuleEngine.add_rules()``. The file may
instead be a mapping with a ``rules`` list and a ``fact_schema`` import string;
the rules are then checked against that model when loaded (see
:mod:`fluxrules.adapters.loaders.rule_file`).

Requires: ``pip install pyyaml``

Example YAML::

    - id: 1
      name: high_value
      priority: 10
      action: flag_for_review
      enabled: true
      conditions:
        type: condition
        field: amount
        op: ">"
        value: 1000
"""

from __future__ import annotations

from typing import Any

from fluxrules.adapters.loaders.rule_file import read_rule_file


def load_rules_from_yaml(
    path: str, *, fact_schema: type | str | None = None
) -> list[dict[str, Any]]:
    """Load rules from a YAML file.

    Args:
        path: Path to the YAML file.
        fact_schema: Model class, or import string (``"myapp.models:Payment"``
            or ``"models.py:Payment"``), to check every rule field against.
            Defaults to the file's own ``fact_schema`` key, if it has one.

    Returns:
        A list of rule dicts ready to pass to ``RuleEngine.add_rules()``.

    Raises:
        ImportError: When ``pyyaml`` is not installed, or the schema cannot be
            imported.
        UnknownFieldError: When a rule names a field the schema lacks.
    """
    from fluxrules.facts import load_schema, schema_info

    document = read_rule_file(path)
    schema = fact_schema if fact_schema is not None else document.fact_schema
    if schema is not None:
        # A string from the file resolves relative to the file's directory.
        model = (
            load_schema(schema, base_dir=document.path.parent)
            if isinstance(schema, str)
            else schema
        )
        schema_info(model).check_rules(document.rules)
    return document.rules
