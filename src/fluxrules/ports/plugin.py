from __future__ import annotations

from typing import Protocol

from fluxrules.engine.pipeline import PipelineStep


class PluginRegistryPort(Protocol):
    def register_rule_type(self, name: str, handler: object) -> None: ...

    def register_pipeline_step(self, name: str, step: PipelineStep[object]) -> None: ...
