from __future__ import annotations

from typing import Protocol

from fluxrules.domain.models import Ruleset


class RulesetRepositoryPort(Protocol):
    def save(self, ruleset: Ruleset) -> None: ...

    def get(self, ruleset_id: str) -> Ruleset | None: ...
