"""Fact transforms for the FluxRules pipeline package."""

from __future__ import annotations

from fluxrules.pipeline.transforms.builtin import (
    Defaults,
    FieldType,
    Flatten,
    Rename,
    Require,
)
from fluxrules.pipeline.transforms.composed import (
    Conditional,
    DropFact,
    Filter,
    MapValues,
    Switch,
)

__all__ = [
    # composed
    "Conditional",
    "Defaults",
    "DropFact",
    "FieldType",
    "Filter",
    # builtin
    "Flatten",
    "MapValues",
    "Rename",
    "Require",
    "Switch",
]
