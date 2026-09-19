"""Entry-point based plugin auto-discovery.

Third-party packages extend FluxRules by advertising objects under dedicated
``importlib.metadata`` entry-point groups in their own ``pyproject.toml``::

    [project.entry-points."fluxrules.operators"]
    within_range = "my_pkg.operators:within_range"

    [project.entry-points."fluxrules.engines"]
    myengine = "my_pkg.engine:MyEngine"

    [project.entry-points."fluxrules.actions"]
    slack_notify = "my_pkg.actions:slack_notify"

    [project.entry-points."fluxrules.transforms"]
    redact = "my_pkg.transforms:Redact"

Call :func:`load_plugins` once at startup to register everything discovered.
Discovery is explicit (never an import side effect) so applications stay in
control of when third-party code is loaded.
"""

from __future__ import annotations

import logging
from importlib import metadata

logger = logging.getLogger(__name__)

#: Supported entry-point groups, in load order.
PLUGIN_GROUPS = (
    "fluxrules.operators",
    "fluxrules.engines",
    "fluxrules.actions",
    "fluxrules.transforms",
)


def _register_operator_ep(name: str, obj: object) -> None:
    from fluxrules.engine import register_operator

    register_operator(name, obj)  # type: ignore[arg-type]


def _register_engine_ep(name: str, obj: object) -> None:
    from fluxrules.engine import register_engine

    register_engine(name, obj, override=True)  # type: ignore[arg-type]


def _register_action_ep(name: str, obj: object) -> None:
    from fluxrules.plugins.actions import action_registry

    action_registry.register(name=name)(obj)


def _register_transform_ep(name: str, obj: object) -> None:
    from fluxrules.pipeline.registry import register as register_transform

    register_transform(obj, name=name)  # type: ignore[arg-type]


_DISPATCH = {
    "fluxrules.operators": _register_operator_ep,
    "fluxrules.engines": _register_engine_ep,
    "fluxrules.actions": _register_action_ep,
    "fluxrules.transforms": _register_transform_ep,
}


def _iter_entry_points(group: str):
    """Yield entry points for a group across importlib.metadata versions."""
    eps = metadata.entry_points()
    # Python 3.10+ SelectableGroups vs. older mapping API.
    if hasattr(eps, "select"):
        return list(eps.select(group=group))
    return list(eps.get(group, []))  # pragma: no cover - legacy API


def load_plugins(groups: tuple[str, ...] = PLUGIN_GROUPS) -> dict[str, list[str]]:
    """Discover and register all entry-point plugins.

    Args:
        groups: Entry-point groups to scan (defaults to all supported groups).

    Returns:
        A mapping of group name to the list of plugin names successfully
        registered. A plugin that fails to load or register is logged and
        skipped rather than aborting discovery.
    """
    loaded: dict[str, list[str]] = {group: [] for group in groups}
    for group in groups:
        register = _DISPATCH.get(group)
        if register is None:
            logger.warning("Unknown FluxRules plugin group: %s", group)
            continue
        for ep in _iter_entry_points(group):
            try:
                obj = ep.load()
                register(ep.name, obj)
            except Exception:
                logger.exception("Failed to load FluxRules plugin %r from group %s", ep.name, group)
                continue
            loaded[group].append(ep.name)
            logger.info("Loaded FluxRules plugin %r from group %s", ep.name, group)
    return loaded
