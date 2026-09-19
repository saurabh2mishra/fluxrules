"""FactPipeline: the heart of the fact transformation framework.

A :class:`FactPipeline` wraps either a single :class:`~fluxrules.pipeline.base.Transform`
or a tree of :class:`CompositionNode` objects built with the ``>>`` (sequence)
and ``|`` (fallback) operators. Pipelines are callable, inspectable,
serializable, observable (with hooks), and resilient (with error policies).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import TYPE_CHECKING, Any

from fluxrules.pipeline.base import Transform

if TYPE_CHECKING:
    from fluxrules.pipeline.error_policy import ErrorPolicy
    from fluxrules.pipeline.observability import ObservabilityHook

__all__ = [
    "CompositionNode",
    "CompositionOperator",
    "FactPipeline",
]


class CompositionOperator(str, Enum):
    """Operators used to compose transforms into a tree."""

    SEQUENCE = "seq"  # a >> b: apply a, then b
    UNION = "union"  # a | b: try a, on error try b
    CONDITIONAL = "cond"  # if predicate(fact): a else b


@dataclass
class CompositionNode:
    """A node in the pipeline composition tree.

    Leaf positions hold :class:`Transform` instances; internal nodes hold an
    operator plus child nodes.
    """

    op: CompositionOperator
    left: Transform | CompositionNode
    right: Transform | CompositionNode | None = None
    predicate: Callable[[dict[str, Any]], bool] | None = None
    on_error_types: tuple[type[Exception], ...] = (Exception,)


class FactPipeline:
    """A composable, inspectable pipeline of fact transforms.

    A pipeline can be:

    - A single transform: ``FactPipeline([Rename(...)])``
    - A sequence: ``a >> b >> c``
    - A union / fallback: ``a | b``
    - A conditional branch: :meth:`when`

    Every pipeline can be called, inspected (:meth:`inspect`), serialized
    (:meth:`to_dict`), and composed with the ``>>`` and ``|`` operators.

    Advanced features:

    - ``hooks``: observability hooks invoked around each transform/pipeline.
    - ``error_policy``: typed handling of transform failures.
    """

    def __init__(
        self,
        transforms: list[Transform] | None = None,
        *,
        root: Transform | CompositionNode | None = None,
        name: str = "default",
        hooks: list[ObservabilityHook] | None = None,
        error_policy: ErrorPolicy | None = None,
    ) -> None:
        """Build a pipeline from a flat list or an explicit composition tree.

        Args:
            transforms: Ordered transforms, composed into a sequence.
            root: A pre-built transform or composition node (advanced use).
            name: Human-readable pipeline name (used in inspection/metrics).
            hooks: Observability hooks for pipeline execution.
            error_policy: Error-handling policy for transform failures.

        Raises:
            ValueError: If neither ``transforms`` nor ``root`` is given, or if
                ``transforms`` is empty.
        """
        if root is not None:
            self.root: Transform | CompositionNode = root
        elif transforms is not None:
            if len(transforms) == 0:
                raise ValueError("Pipeline must have at least one transform")
            node: Transform | CompositionNode = transforms[0]
            for transform in transforms[1:]:
                node = CompositionNode(
                    op=CompositionOperator.SEQUENCE,
                    left=node,
                    right=transform,
                )
            self.root = node
        else:
            raise ValueError("Either transforms or root must be provided")

        self.name = name
        self.hooks: list[ObservabilityHook] = hooks or []
        self.error_policy = error_policy

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        """Apply the pipeline to ``fact`` and return the transformed result."""
        self._emit("on_pipeline_start", self.name, fact)
        start = perf_counter()
        try:
            result = self._eval(self.root, fact)
        except Exception as error:
            self._emit("on_pipeline_error", self.name, fact, error)
            raise
        self._emit("on_pipeline_end", self.name, fact, perf_counter() - start)
        return result

    def _eval(self, node: Transform | CompositionNode, fact: dict[str, Any]) -> dict[str, Any]:
        """Recursively evaluate a node of the composition tree."""
        if isinstance(node, Transform):
            return self._run_transform(node, fact)

        if node.op is CompositionOperator.SEQUENCE:
            left_result = self._eval(node.left, fact)
            assert node.right is not None  # sequence always has a right child
            return self._eval(node.right, left_result)

        if node.op is CompositionOperator.UNION:
            try:
                return self._eval(node.left, fact)
            except node.on_error_types:
                assert node.right is not None
                return self._eval(node.right, fact)

        if node.op is CompositionOperator.CONDITIONAL:
            assert node.predicate is not None
            if node.predicate(fact):
                return self._eval(node.left, fact)
            return self._eval(node.right, fact) if node.right is not None else fact

        raise ValueError(f"Unknown composition op: {node.op}")  # pragma: no cover

    def _run_transform(self, transform: Transform, fact: dict[str, Any]) -> dict[str, Any]:
        """Execute one transform with hooks and the configured error policy."""
        attempt = 0
        while True:
            self._emit("on_transform_start", transform, fact)
            start = perf_counter()
            try:
                result = transform(fact)
            except Exception as error:
                self._emit("on_transform_error", transform, fact, error)
                decision = self._handle_error(transform, fact, error, attempt)
                if decision is _RAISE:
                    raise
                if decision is _SKIP:
                    raise _SkipRecord(transform.metadata.name) from error
                if decision is _RETRY:
                    attempt += 1
                    continue
                # Fallback dict
                return decision  # type: ignore[return-value]
            self._emit("on_transform_end", transform, fact, perf_counter() - start)
            return result

    def _handle_error(
        self,
        transform: Transform,
        fact: dict[str, Any],
        error: Exception,
        attempt: int,
    ) -> object:
        """Consult the error policy and return a sentinel or a fallback dict."""
        if self.error_policy is None:
            return _RAISE

        from fluxrules.pipeline.error_policy import ErrorAction

        decision = self.error_policy.decide(error, fact)
        if decision.action is ErrorAction.FAIL:
            return _RAISE
        if decision.action is ErrorAction.SKIP:
            return _SKIP
        if decision.action is ErrorAction.RETRY:
            if attempt < self.error_policy.max_retries:
                self.error_policy.sleep_before_retry(attempt + 1)
                return _RETRY
            return _RAISE
        # FALLBACK
        return decision.fallback if decision.fallback is not None else _RAISE

    def _emit(self, method: str, *args: Any) -> None:
        """Invoke ``method`` on every hook that implements it, defensively."""
        for hook in self.hooks:
            handler = getattr(hook, method, None)
            if callable(handler):
                handler(*args)

    # ------------------------------------------------------------------
    # Composition operators
    # ------------------------------------------------------------------

    def __rshift__(self, other: FactPipeline | Transform) -> FactPipeline:
        """``a >> b``: run ``a``, then feed its output into ``b``."""
        right, right_name = self._as_node(other)
        return FactPipeline(
            root=CompositionNode(
                op=CompositionOperator.SEQUENCE,
                left=self.root,
                right=right,
            ),
            name=f"{self.name}_then_{right_name}",
            hooks=self.hooks,
            error_policy=self.error_policy,
        )

    def __or__(self, other: FactPipeline | Transform) -> FactPipeline:
        """``a | b``: try ``a``; if it raises, run ``b`` on the original fact."""
        right, right_name = self._as_node(other)
        return FactPipeline(
            root=CompositionNode(
                op=CompositionOperator.UNION,
                left=self.root,
                right=right,
            ),
            name=f"{self.name}_or_{right_name}",
            hooks=self.hooks,
            error_policy=self.error_policy,
        )

    def when(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        then: FactPipeline | Transform,
        otherwise: FactPipeline | Transform | None = None,
    ) -> FactPipeline:
        """Branch on ``predicate``: run ``then`` if true, else ``otherwise``.

        When ``otherwise`` is omitted, the fact passes through unchanged on the
        false branch.
        """
        then_node, then_name = self._as_node(then)
        else_node: Transform | CompositionNode | None = None
        else_name = "passthrough"
        if otherwise is not None:
            else_node, else_name = self._as_node(otherwise)
        branch = CompositionNode(
            op=CompositionOperator.CONDITIONAL,
            left=then_node,
            right=else_node,
            predicate=predicate,
        )
        return FactPipeline(
            root=CompositionNode(
                op=CompositionOperator.SEQUENCE,
                left=self.root,
                right=branch,
            ),
            name=f"{self.name}_when_{then_name}_else_{else_name}",
            hooks=self.hooks,
            error_policy=self.error_policy,
        )

    @staticmethod
    def _as_node(
        other: FactPipeline | Transform,
    ) -> tuple[Transform | CompositionNode, str]:
        """Normalize a pipeline or transform into a (node, name) pair.

        Raises:
            TypeError: If ``other`` is neither a :class:`FactPipeline` nor a
                :class:`Transform` (e.g. a plain function or lambda). Failing
                here gives a clear message instead of a late ``AttributeError``
                when the pipeline is eventually called.
        """
        if isinstance(other, FactPipeline):
            return other.root, other.name
        if isinstance(other, Transform):
            return other, type(other).__name__
        raise TypeError(
            "Pipeline composition (>>, |, .when) requires a Transform or "
            f"FactPipeline, got {type(other).__name__!r}. Wrap plain functions "
            "in a Transform subclass first."
        )

    # ------------------------------------------------------------------
    # Introspection & serialization
    # ------------------------------------------------------------------

    def transforms(self) -> list[Transform]:
        """Return all transforms in left-to-right tree order."""
        return self._collect_transforms(self.root)

    def inspect(self) -> dict[str, Any]:
        """Return full introspection: per-transform and aggregated metadata."""
        transforms = self.transforms()
        all_input_fields: set[str] = set()
        all_output_fields: set[str] = set()
        all_errors: set[str] = set()
        for transform in transforms:
            meta = transform.metadata
            all_input_fields.update(meta.required_input_fields)
            all_output_fields.update(meta.output_fields)
            all_errors.update(error.__name__ for error in meta.errors_raised)
        return {
            "name": self.name,
            "num_transforms": len(transforms),
            "transforms": [
                {
                    "name": t.metadata.name,
                    "version": t.metadata.version,
                    "required_input": t.metadata.required_input_fields,
                    "output": t.metadata.output_fields,
                    "errors": [e.__name__ for e in t.metadata.errors_raised],
                    "signature": t.metadata.signature,
                }
                for t in transforms
            ],
            "aggregated": {
                "all_input_fields": sorted(all_input_fields),
                "all_output_fields": sorted(all_output_fields),
                "all_errors": sorted(all_errors),
            },
        }

    def _collect_transforms(self, node: Transform | CompositionNode) -> list[Transform]:
        """Recursively collect transforms from a node in tree order."""
        if isinstance(node, Transform):
            return [node]
        result: list[Transform] = []
        result.extend(self._collect_transforms(node.left))
        if node.right is not None:
            result.extend(self._collect_transforms(node.right))
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pipeline to a JSON-friendly dict."""
        return {
            "name": self.name,
            "root": self._serialize_node(self.root),
        }

    def _serialize_node(self, node: Transform | CompositionNode) -> dict[str, Any]:
        """Recursively serialize a node of the composition tree."""
        if isinstance(node, Transform):
            return node.to_dict()
        return {
            "type": "composition",
            "op": node.op.value,
            "left": self._serialize_node(node.left),
            "right": self._serialize_node(node.right) if node.right else None,
        }

    @classmethod
    def from_dict(
        cls,
        spec: dict[str, Any],
        *,
        registry: Any | None = None,
    ) -> FactPipeline:
        """Reconstruct a pipeline from :meth:`to_dict` output.

        Requires a :class:`~fluxrules.pipeline.registry.TransformRegistry` so
        transform type names can be resolved back to classes. If ``registry``
        is omitted, the default global registry is used.
        """
        if registry is None:
            from fluxrules.pipeline.registry import default_registry

            registry = default_registry()
        root = cls._deserialize_node(spec["root"], registry)
        return cls(root=root, name=spec.get("name", "default"))

    @classmethod
    def _deserialize_node(cls, spec: dict[str, Any], registry: Any) -> Transform | CompositionNode:
        """Recursively rebuild a node from its serialized form."""
        if spec.get("type") == "composition":
            left = cls._deserialize_node(spec["left"], registry)
            right = cls._deserialize_node(spec["right"], registry) if spec.get("right") else None
            return CompositionNode(
                op=CompositionOperator(spec["op"]),
                left=left,
                right=right,
            )
        return registry.deserialize(spec)

    def __repr__(self) -> str:
        return f"FactPipeline(name={self.name!r}, transforms={len(self.transforms())})"


# Internal sentinels for the error-policy decision in _run_transform.
class _SkipRecord(Exception):
    """Raised internally to signal that a record should be skipped."""


_RAISE = object()
_SKIP = object()
_RETRY = object()
