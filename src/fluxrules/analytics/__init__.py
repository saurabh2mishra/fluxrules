"""FluxRules analytics - re-exports from ``fluxrules.api.analytics``.

Provides a convenience import path so users can write::

    from fluxrules.analytics import CoverageReporter, ExplanationEngine
"""

from fluxrules.api.analytics.coverage_report import RuntimeCoverageReport
from fluxrules.api.analytics.explanation_engine import ExplanationEngine

__all__ = ["ExplanationEngine", "RuntimeCoverageReport"]
