"""Fact sources and the loader (the "Dataset" + "DataLoader" analogues).

Format knowledge lives in small, explicit :class:`FactSource` implementations
(no format sniffing). :class:`FactLoader` owns the generic plumbing -
iteration, error policy, and batching - and feeds raw dicts through a
:class:`~fluxrules.pipeline.core.FactPipeline`.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from fluxrules.pipeline.core import FactPipeline, _SkipRecord
from fluxrules.pipeline.transforms.composed import DropFact

if TYPE_CHECKING:
    from fluxrules.pipeline.error_policy import ErrorPolicy

__all__ = [
    "CSVSource",
    "FactLoader",
    "FactSource",
    "IterableSource",
    "JSONSource",
    "ValidatedFactLoader",
]


@runtime_checkable
class FactSource(Protocol):
    """Yields raw dicts. The format choice is explicit at the call site."""

    def read(self) -> Iterator[dict[str, Any]]:
        """Yield raw fact dictionaries one at a time."""
        ...


@dataclass
class IterableSource:
    """Wrap an in-memory list or generator - the 90% case."""

    items: Iterable[dict[str, Any]]

    def read(self) -> Iterator[dict[str, Any]]:
        yield from self.items


@dataclass
class JSONSource:
    """Read a JSON object/array from a string or a file path."""

    text: str
    is_path: bool = False

    def read(self) -> Iterator[dict[str, Any]]:
        if self.is_path:
            with open(self.text) as handle:
                raw = handle.read()
        else:
            raw = self.text
        data = json.loads(raw)
        yield from (data if isinstance(data, list) else [data])


@dataclass
class CSVSource:
    """Read CSV rows as dicts from a string or a file path."""

    text: str
    is_path: bool = False

    def read(self) -> Iterator[dict[str, Any]]:
        handle = open(self.text, newline="") if self.is_path else io.StringIO(self.text)
        with handle as f:
            yield from csv.DictReader(f)


@dataclass
class FactLoader:
    """Iterate a source through a pipeline with an explicit error policy.

    The loader honours both:

    - The ``on_error`` string (``"raise"`` | ``"skip"`` | ``"collect"``).
    - The pipeline's typed :class:`ErrorPolicy`, when configured. Skips
      requested by the policy (or by :class:`DropFact` filters) drop the record
      from the output stream without raising.
    """

    source: FactSource
    pipeline: FactPipeline
    on_error: str = "raise"  # "raise" | "skip" | "collect"
    dead_letter: list[dict[str, Any]] = field(default_factory=list)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for raw in self.source.read():
            try:
                yield self.pipeline(raw)
            except (_SkipRecord, DropFact):
                # Policy- or Filter-driven skip: drop silently, no dead-letter.
                continue
            except Exception as error:
                if self.on_error == "raise":
                    raise
                if self.on_error == "collect":
                    self.dead_letter.append({"raw": raw, "error": str(error)})
                # "skip" -> drop silently

    def batch(self, size: int) -> Iterator[list[dict[str, Any]]]:
        """Yield facts in lists of at most ``size`` (DataLoader-style)."""
        if size < 1:
            raise ValueError("batch size must be >= 1")
        buffer: list[dict[str, Any]] = []
        for fact in self:
            buffer.append(fact)
            if len(buffer) >= size:
                yield buffer
                buffer = []
        if buffer:
            yield buffer


@dataclass
class ValidatedFactLoader(FactLoader):
    """FactLoader that validates each raw fact against a schema first.

    Validation happens at the boundary, before transforms run:

        raw -> validate_facts(schema, raw) -> pipeline(validated) -> yield

    ``schema=None`` behaves exactly like :class:`FactLoader`.
    """

    schema: type[Any] | None = None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for raw in self.source.read():
            try:
                if self.schema is not None:
                    # Lazy import keeps pydantic optional for users that do
                    # not opt into schema validation.
                    from fluxrules.pipeline.schema import validate_facts

                    validated = validate_facts(self.schema, raw)
                else:
                    validated = raw

                yield self.pipeline(validated)
            except (_SkipRecord, DropFact):
                continue
            except Exception as error:
                if self.on_error == "raise":
                    raise
                if self.on_error == "collect":
                    self.dead_letter.append({"raw": raw, "error": str(error)})
                # "skip" -> drop silently


def with_policy(
    source: FactSource,
    pipeline: FactPipeline,
    policy: ErrorPolicy,
    *,
    on_error: str = "raise",
) -> FactLoader:
    """Convenience: bind ``policy`` onto ``pipeline`` then build a loader."""
    pipeline.error_policy = policy
    return FactLoader(source=source, pipeline=pipeline, on_error=on_error)
