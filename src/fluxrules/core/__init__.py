"""FluxRules Core - pure-Python rule engine with zero external dependencies (except python-sat for validation)."""

from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.phreak import PhreakEngine as RuleEngine

__all__ = [
    "EngineConfig",
    "RuleEngine",
    "get_config",
    "set_config",
]
