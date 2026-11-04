"""Read YAML values as they are written.

PyYAML follows YAML 1.1, where an unquoted ``NO`` is the boolean ``False``,
``0755`` is the octal number 493, ``1:30`` is 90 (minutes and seconds), and
``1e3`` is the text ``"1e3"``. A rule ``country == NO`` written for Norway
then compares with ``False`` and never matches. FluxRules reads its YAML files
(rule files and config files) by YAML 1.2's rules instead, so a value means
what it looks like:

- only ``true`` and ``false`` (also ``True``, ``TRUE``, ``False``, ``FALSE``)
  are booleans; ``yes``, ``no``, ``on``, ``off`` and the rest are text;
- an integer is ``5``, ``-3``, ``0o755`` (octal) or ``0x1F`` (hex); one with a
  leading zero (``0755``) or a colon (``1:30``) is text;
- ``1e3``, ``1.5`` and ``.5`` are numbers, as are ``.inf`` and ``.nan``;
- ``null``, ``~`` and an empty value are ``None``; ``2024-05-01`` is a date,
  as before.

Each value that FluxRules 1.1 read differently warns once with
:class:`~fluxrules.domain.errors.YamlValueWarning`, naming the file and line.
"""

from __future__ import annotations

import math
import re
import warnings
from typing import Any

from fluxrules.domain.errors import YamlValueWarning
from fluxrules.utils.warn import caller_stacklevel

__all__ = ["load_yaml"]

_BOOL = "tag:yaml.org,2002:bool"
_INT = "tag:yaml.org,2002:int"
_FLOAT = "tag:yaml.org,2002:float"
_STR = "tag:yaml.org,2002:str"

_BOOL_RE = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_RE = re.compile(r"^(?:[-+]?(?:0|[1-9][0-9]*)|0o[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+\.[0-9]*)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?[0-9]+[eE][-+]?[0-9]+"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)


def _construct_bool(loader: Any, node: Any) -> bool:
    return bool(loader.construct_scalar(node).lower() == "true")


def _construct_int(loader: Any, node: Any) -> int:
    return int(loader.construct_scalar(node), 0)


def _construct_float(loader: Any, node: Any) -> float:
    text = loader.construct_scalar(node).lower()
    sign = -1.0 if text.startswith("-") else 1.0
    body = text.lstrip("+-")
    if body == ".inf":
        return sign * math.inf
    if body == ".nan":
        return math.nan
    return float(text)


_loaders: dict[str, type] = {}


def _loader_classes() -> tuple[type, type]:
    """The YAML 1.2 loader, and PyYAML's own for comparison (built once)."""
    if not _loaders:
        import yaml  # type: ignore[import-untyped]

        class Loader(yaml.SafeLoader):
            pass

        # Drop YAML 1.1's boolean and number patterns; keep null, dates and
        # the rest.
        Loader.yaml_implicit_resolvers = {
            first: [(tag, rx) for tag, rx in resolvers if tag not in (_BOOL, _INT, _FLOAT)]
            for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }
        Loader.add_implicit_resolver(_BOOL, _BOOL_RE, list("tTfF"))
        Loader.add_implicit_resolver(_INT, _INT_RE, list("-+0123456789"))
        Loader.add_implicit_resolver(_FLOAT, _FLOAT_RE, list("-+0123456789."))
        Loader.add_constructor(_BOOL, _construct_bool)
        Loader.add_constructor(_INT, _construct_int)
        Loader.add_constructor(_FLOAT, _construct_float)
        _loaders["new"] = Loader
        _loaders["old"] = yaml.SafeLoader
    return _loaders["new"], _loaders["old"]


def load_yaml(stream: Any, *, source: str) -> Any:
    """Parse one YAML document from *stream*, reading values as written.

    *source* names the file in warnings. Raises ``yaml.YAMLError`` for YAML
    that does not parse.
    """
    new_cls, old_cls = _loader_classes()
    loader = new_cls(stream)
    try:
        node = loader.get_single_node()
        if node is None:
            return None
        data = loader.construct_document(node)
        _warn_changed(node, loader, old_cls(""), source)
        return data
    finally:
        loader.dispose()


def _warn_changed(root: Any, loader: Any, old: Any, source: str) -> None:
    """Warn for every plain scalar that YAML 1.1 read differently."""
    import yaml  # type: ignore[import-untyped]

    changed = []
    stack = [root]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                stack.extend((value, key))
            continue
        if isinstance(node, yaml.SequenceNode):
            stack.extend(reversed(node.value))
            continue
        if not isinstance(node, yaml.ScalarNode) or node.style is not None:
            continue  # quoted and block scalars are always text
        old_tag = old.resolve(yaml.ScalarNode, node.value, (True, False))
        if old_tag == node.tag:
            continue
        new_value = loader.construct_object(node)
        old_value = old.construct_object(yaml.ScalarNode(old_tag, node.value))
        changed.append((node, new_value, old_value))
    changed.sort(key=lambda item: (item[0].start_mark.line, item[0].start_mark.column))
    for node, new_value, old_value in changed:
        _warn(source, node, new_value, old_value)


def _warn(source: str, node: Any, new_value: Any, old_value: Any) -> None:
    text = node.value
    if isinstance(new_value, str):
        fix = f"Write {_literal(old_value)} if you mean {_describe(old_value)}."
    else:
        fix = f'Write "{text}" in quotes if you mean the text.'
    warnings.warn(
        f"{source}, line {node.start_mark.line + 1}: {text} is read as "
        f"{_describe(new_value)}; FluxRules 1.1 read it as {_describe(old_value)}. {fix}",
        YamlValueWarning,
        stacklevel=caller_stacklevel(),
    )


def _describe(value: Any) -> str:
    if isinstance(value, bool):
        return f"the boolean {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"the number {_literal(value)}"
    if isinstance(value, str):
        return f'the text "{value}"'
    return repr(value)


def _literal(value: Any) -> str:
    """*value* as it would be written in YAML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return ".nan"
        if math.isinf(value):
            return ".inf" if value > 0 else "-.inf"
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)
