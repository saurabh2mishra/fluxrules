from __future__ import annotations

from typing import Protocol


class TracerPort(Protocol):
    def on_evaluation_start(self, ruleset_id: str) -> None: ...

    def on_evaluation_end(self, ruleset_id: str, matched_count: int) -> None: ...
