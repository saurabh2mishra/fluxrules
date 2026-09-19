"""API-specific engine adapter with caching, database, and metrics support.

This module provides the APIEngineAdapter which wraps the main
fluxrules.engine module with API-specific features:
- Rule caching (Redis + local)
- Metrics collection
- Result formatting
- Database integration

The main fluxrules.engine module provides the engine implementations.
"""

from fluxrules.api.engines.adapter import APIEngineAdapter, RuleCache
from fluxrules.api.engines.engine_pool import RuleEnginePool, rules_signature

__all__ = ["APIEngineAdapter", "RuleCache", "RuleEnginePool", "rules_signature"]
