"""Pipeline versioning and breaking-change detection.

Tracks the structural "fingerprint" of a pipeline so changes can be audited and
classified as compatible (additive) or breaking. The fingerprint is derived
from each transform's :class:`~fluxrules.pipeline.base.TransformMetadata`
signature, so renames, version bumps, or field-contract changes are detected
deterministically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxrules.pipeline.core import FactPipeline

__all__ = [
    "ChangeType",
    "PipelineVersion",
    "VersionDiff",
    "diff_pipelines",
]


class ChangeType(str, Enum):
    """Classification of the difference between two pipeline versions."""

    IDENTICAL = "identical"
    COMPATIBLE = "compatible"  # additive only (new output fields)
    BREAKING = "breaking"  # removed outputs, new required inputs, or reorders


@dataclass(frozen=True)
class PipelineVersion:
    """Immutable structural snapshot of a pipeline.

    Build one with :meth:`from_pipeline`; compare two with
    :func:`diff_pipelines`.
    """

    name: str
    version: str
    fingerprint: str
    transform_signatures: tuple[str, ...]
    transform_order: tuple[str, ...]
    required_input_fields: frozenset[str]
    output_fields: frozenset[str]

    @classmethod
    def from_pipeline(cls, pipeline: FactPipeline, version: str = "1.0.0") -> PipelineVersion:
        """Compute a :class:`PipelineVersion` from a live pipeline."""
        transforms = pipeline.transforms()
        signatures = tuple(t.metadata.signature for t in transforms)
        order = tuple(t.metadata.name for t in transforms)
        required: set[str] = set()
        outputs: set[str] = set()
        for transform in transforms:
            required.update(transform.metadata.required_input_fields)
            outputs.update(transform.metadata.output_fields)
        fingerprint_payload = json.dumps(
            {
                "name": pipeline.name,
                "version": version,
                "signatures": list(signatures),
            },
            sort_keys=True,
        )
        fingerprint = hashlib.sha256(fingerprint_payload.encode()).hexdigest()[:12]
        return cls(
            name=pipeline.name,
            version=version,
            fingerprint=fingerprint,
            transform_signatures=signatures,
            transform_order=order,
            required_input_fields=frozenset(required),
            output_fields=frozenset(outputs),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of this version."""
        return {
            "name": self.name,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "transform_signatures": list(self.transform_signatures),
            "transform_order": list(self.transform_order),
            "required_input_fields": sorted(self.required_input_fields),
            "output_fields": sorted(self.output_fields),
        }


@dataclass(frozen=True)
class VersionDiff:
    """Result of comparing two :class:`PipelineVersion` objects."""

    change_type: ChangeType
    added_outputs: frozenset[str]
    removed_outputs: frozenset[str]
    added_required_inputs: frozenset[str]
    removed_required_inputs: frozenset[str]

    @property
    def is_breaking(self) -> bool:
        """True if the change would break existing consumers."""
        return self.change_type is ChangeType.BREAKING


def diff_pipelines(old: PipelineVersion, new: PipelineVersion) -> VersionDiff:
    """Classify the change from ``old`` to ``new``.

    Breaking changes are: removed output fields, newly required input fields,
    or any change to the ordered list of transforms (e.g. a reorder, removal,
    or insertion). Purely additive output fields are compatible.
    """
    added_outputs = new.output_fields - old.output_fields
    removed_outputs = old.output_fields - new.output_fields
    added_required = new.required_input_fields - old.required_input_fields
    removed_required = old.required_input_fields - new.required_input_fields

    if old.fingerprint == new.fingerprint:
        change_type = ChangeType.IDENTICAL
    elif removed_outputs or added_required or old.transform_order != new.transform_order:
        change_type = ChangeType.BREAKING
    else:
        change_type = ChangeType.COMPATIBLE

    return VersionDiff(
        change_type=change_type,
        added_outputs=frozenset(added_outputs),
        removed_outputs=frozenset(removed_outputs),
        added_required_inputs=frozenset(added_required),
        removed_required_inputs=frozenset(removed_required),
    )
