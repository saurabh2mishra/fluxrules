"""FluxRules FactPipeline - a type-safe, composable fact transformation framework.

A PyTorch-DataLoader-style approach to getting heterogeneous facts (in-memory,
JSON, CSV, streams) into the engine without dual-YAML schemas or god-classes.
Three concerns are separated:

- :class:`FactSource` - *you* own the format knowledge (explicit, tiny).
- :class:`FactPipeline` - small, composable, testable transforms.
- :class:`FactLoader` - the framework owns iteration, error policy, batching.

Features:

- **Type Safety & Composition:** :class:`Transform` ABC, composition operators
  (``>>``, ``|``), introspection, and serialization.
- **Observability & Error Handling:** :class:`ObservabilityHook`, :class:`PipelineMetrics`,
  and a typed :class:`ErrorPolicy`.
- **Enterprise Features:** :class:`TransformRegistry` (round-trip serialization),
  :class:`PipelineVersion` (breaking-change detection), and advanced transforms
  (:class:`Conditional`, :class:`Filter`, :class:`Switch`, :class:`MapValues`).

Example:
    >>> from fluxrules.pipeline import FactPipeline, Flatten, Rename, Require
    >>> normalize = FactPipeline([
    ...     Flatten(),
    ...     Rename({"user_id": ["user.id", "userId"]}),
    ...     Require(["user_id"]),
    ... ])
    >>> normalize({"user": {"id": "u_1"}})
    {'user.id': 'u_1', 'user_id': 'u_1'}
"""

from __future__ import annotations

from fluxrules.pipeline.base import Transform, TransformMetadata
from fluxrules.pipeline.core import (
    CompositionNode,
    CompositionOperator,
    FactPipeline,
)
from fluxrules.pipeline.error_policy import (
    ErrorAction,
    ErrorDecision,
    ErrorPolicy,
)
from fluxrules.pipeline.exporters import (
    OpenTelemetryHook,
    PrometheusHook,
)
from fluxrules.pipeline.loaders import (
    CSVSource,
    FactLoader,
    FactSource,
    IterableSource,
    JSONSource,
    ValidatedFactLoader,
)
from fluxrules.pipeline.observability import (
    LoggingHook,
    MetricsHook,
    ObservabilityHook,
    PipelineMetrics,
)
from fluxrules.pipeline.registry import (
    TransformRegistry,
    default_registry,
    register,
)
from fluxrules.pipeline.schema import (
    FactSchema,
    SchemaValidationError,
    validate_facts,
)
from fluxrules.pipeline.transforms import (
    Conditional,
    Defaults,
    DropFact,
    FieldType,
    Filter,
    Flatten,
    MapValues,
    Rename,
    Require,
    Switch,
)
from fluxrules.pipeline.utils.dict_utils import (
    ListStrategy,
    flatten_dict,
)
from fluxrules.pipeline.validators import (
    FactValidator,
    InvalidFactError,
)
from fluxrules.pipeline.versioning import (
    ChangeType,
    PipelineVersion,
    VersionDiff,
    diff_pipelines,
)

__all__ = [
    "CSVSource",
    "ChangeType",
    "CompositionNode",
    "CompositionOperator",
    # Composed transforms
    "Conditional",
    "Defaults",
    "DropFact",
    "ErrorAction",
    "ErrorDecision",
    # Error policy
    "ErrorPolicy",
    "FactLoader",
    # Core
    "FactPipeline",
    "FactSchema",
    # Loaders
    "FactSource",
    "FactValidator",
    "FieldType",
    "Filter",
    # Builtin transforms
    "Flatten",
    "InvalidFactError",
    "IterableSource",
    "JSONSource",
    "ListStrategy",
    "LoggingHook",
    "MapValues",
    "MetricsHook",
    # Observability
    "ObservabilityHook",
    "OpenTelemetryHook",
    "PipelineMetrics",
    # Versioning
    "PipelineVersion",
    # Exporters (external backends)
    "PrometheusHook",
    "Rename",
    "Require",
    "SchemaValidationError",
    "Switch",
    # Base
    "Transform",
    "TransformMetadata",
    # Registry
    "TransformRegistry",
    "ValidatedFactLoader",
    "VersionDiff",
    "default_registry",
    "diff_pipelines",
    # Utils
    "flatten_dict",
    "register",
    "validate_facts",
]
