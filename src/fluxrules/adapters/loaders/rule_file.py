"""Rule files - read JSON or YAML rule files, with an optional fact schema.

A rule file holds one of:

- a list of rule mappings,
- a single rule mapping,
- a mapping with a ``rules`` list and an optional ``fact_schema`` import string
  naming the model the rules are written against::

      fact_schema: myapp.models:Payment
      rules:
        - id: 1
          name: high_value
          action: review
          conditions: {type: condition, field: amount, op: ">", value: 1000}

``.json`` files are read as JSON; anything else as YAML (which needs
``pip install pyyaml``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Top-level keys of the ``rules`` + ``fact_schema`` form.
_DOCUMENT_KEYS = frozenset({"rules", "fact_schema"})


@dataclass(frozen=True)
class RuleFile:
    """A parsed rule file.

    Attributes:
        path: the file read.
        rules: the rule mappings, unvalidated.
        fact_schema: the file's ``fact_schema`` import string, or ``None``.
    """

    path: Path
    rules: list[dict[str, Any]]
    fact_schema: str | None = None


def read_rule_file(path: str | Path) -> RuleFile:
    """Read a JSON or YAML rule file.

    Raises:
        ImportError: for a YAML file when ``pyyaml`` is not installed.
        ValueError: when the file is not one of the shapes above.
    """
    path = Path(path)
    with open(path) as f:
        if path.suffix.lower() == ".json":
            data = json.load(f)
        else:
            try:
                import yaml  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "pyyaml is required for YAML rule loading. Install it with: pip install pyyaml"
                ) from exc
            data = yaml.safe_load(f)
    return parse_rule_document(data, path)


def parse_rule_document(data: Any, path: str | Path = "<rules>") -> RuleFile:
    """Split parsed file content into rule mappings and the fact schema.

    Raises:
        ValueError: when *data* is not one of the accepted shapes.
    """
    path = Path(path)
    schema = None
    # A rule mapping never has a "rules" key, so it marks the document form.
    if isinstance(data, dict) and "rules" in data:
        extra = set(data) - _DOCUMENT_KEYS
        if extra:
            raise ValueError(
                f"{path}: unexpected top-level keys {sorted(extra)}; a rule file with "
                "'rules' may only also have 'fact_schema'"
            )
        rules, schema = data["rules"], data.get("fact_schema")
        if not isinstance(rules, list):
            raise ValueError(f"{path}: 'rules' must be a list of rule mappings")
        if schema is not None and not isinstance(schema, str):
            raise ValueError(
                f"{path}: 'fact_schema' must be an import string such as 'myapp.models:Payment'"
            )
    elif isinstance(data, list):
        rules = data
    elif isinstance(data, dict):
        rules = [data]
    elif data is None:
        rules = []
    else:
        raise ValueError(f"{path}: expected a rule mapping or a list of rule mappings")
    return RuleFile(path=path, rules=rules, fact_schema=schema)
