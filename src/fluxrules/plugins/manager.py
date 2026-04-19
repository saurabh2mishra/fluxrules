from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import entry_points


@dataclass
class PluginRegistry:
    rule_types: dict[str, object] = field(default_factory=dict)
    pipeline_steps: dict[str, object] = field(default_factory=dict)

    def register_rule_type(self, name: str, handler: object) -> None:
        self.rule_types[name] = handler

    def register_pipeline_step(self, name: str, step: object) -> None:
        self.pipeline_steps[name] = step


class PluginManager:
    group = "fluxrules.plugins"

    def __init__(self):
        self.registry = PluginRegistry()

    def load_entrypoints(self) -> PluginRegistry:
        for ep in entry_points(group=self.group):
            register = ep.load()
            register(self.registry)
        return self.registry
