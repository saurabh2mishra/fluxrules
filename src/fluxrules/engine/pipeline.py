from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
PipelineStep = Callable[[T], T]


class ExecutionPipeline:
    def __init__(self, steps: list[PipelineStep[T]] | None = None):
        self._steps = steps or []

    def add(self, step: PipelineStep[T]) -> None:
        self._steps.append(step)

    def run(self, payload: T) -> T:
        current = payload
        for step in self._steps:
            current = step(current)
        return current
