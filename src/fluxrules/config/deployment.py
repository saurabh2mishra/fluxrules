"""Deployment configuration with a multi-source loading strategy.

Sources (in precedence order):
    1. **Explicit** - ``DeploymentConfig(...)`` in code
    2. **File-based** - ``DeploymentConfig.from_file("fluxrules.yaml")``
    3. **Environment** - ``DeploymentConfig.from_environment()``
    4. **Auto-detect** - ``DeploymentConfig.load_with_fallback()``

Usage::

    # Explicit (recommended for library users)
    config = DeploymentConfig(
        deployment_type="multi_instance",
        max_rules=100_000,
        instance_count=3,
    )

    # Zero-config fallback
    config = DeploymentConfig.load_with_fallback()
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DeploymentType(Enum):
    """Deployment topology.

    Use these values when constructing :class:`DeploymentConfig`
    for full IDE auto-complete and type-safety.
    """

    SINGLE = "single"
    """Single process / single machine."""

    MULTI_INSTANCE = "multi_instance"
    """Multiple instances in the same data-centre."""

    MULTI_REGION = "multi_region"
    """Instances spread across regions."""

    SERVERLESS = "serverless"
    """Serverless / ephemeral (AWS Lambda, Cloud Functions, etc.)."""


# Canonical string values accepted for ``deployment_type``.
_VALID_DEPLOYMENT_TYPES = {dt.value for dt in DeploymentType}


class ConfigValidationError(ValueError):
    """Raised when a :class:`DeploymentConfig` fails validation."""


@dataclass
class DeploymentConfig:
    """Deployment-level configuration controlling ID generation strategy.

    All fields have sensible defaults suitable for a single-instance
    development deployment.

    Supports construction from four sources (in precedence order):

    1. **Explicit** - ``DeploymentConfig(deployment_type=DeploymentType.MULTI_INSTANCE, ...)``
    2. **File** - ``DeploymentConfig.from_file("fluxrules.yaml")``
    3. **Environment** - ``DeploymentConfig.from_environment()``
    4. **Auto-detect** - ``DeploymentConfig.load_with_fallback()``
    """

    # ── topology ─────────────────────────────────────────────
    deployment_type: str | DeploymentType = DeploymentType.SINGLE
    """Deployment topology.  Accepts a :class:`DeploymentType` enum **or**
    one of the string literals ``'single'``, ``'multi_instance'``,
    ``'multi_region'``, ``'serverless'``."""

    instance_count: int = 1
    """Number of running instances."""

    region_count: int = 1
    """Number of regions / data-centres."""

    # ── scale ────────────────────────────────────────────────
    max_rules: int = 50_000
    """Expected maximum number of rules."""

    expected_growth: str = "stable"
    """``'stable'``, ``'growing'``, or ``'explosive'``."""

    # ── requirements (boolean flags) ─────────────────────────
    requires_sortable_ids: bool = False
    """IDs must be sortable by creation time."""

    requires_deterministic: bool = False
    """IDs must be reproducible given the same input."""

    requires_human_readable: bool = False
    """IDs should be human-readable in logs."""

    require_no_coordination: bool = False
    """Cannot use Redis or other external coordination service."""

    # ── constraints ──────────────────────────────────────────
    storage_sensitive: bool = False
    latency_sensitive: bool = False

    # ── advanced ─────────────────────────────────────────────
    machine_id: int | None = None
    """Pre-assigned machine ID for Snowflake / Hybrid."""

    instance_id: int | None = None
    """Pre-assigned instance ID for Hybrid."""

    redis_host: str = "localhost"
    redis_port: int = 6379

    # ── metadata ─────────────────────────────────────────────
    detected_from: str = "explicit"
    """Source of this configuration (``'explicit'``, ``'file'``, ``'environment'``,
    ``'kubernetes'``, ``'auto'``)."""

    def __post_init__(self) -> None:
        # Normalise deployment_type to string for uniform downstream usage.
        if isinstance(self.deployment_type, DeploymentType):
            self.deployment_type = self.deployment_type.value

    # Validation

    def validate(self) -> list[str]:
        """Validate configuration consistency.

        Returns
        -------
        list[str]
            Human-readable list of validation warnings.  An empty list
            means the configuration is valid.

        Raises
        ------
        ConfigValidationError
            For hard errors that would cause runtime failures.
        """
        warnings: list[str] = []
        dt = str(self.deployment_type)

        # Hard errors
        if dt not in _VALID_DEPLOYMENT_TYPES:
            raise ConfigValidationError(
                f"Invalid deployment_type={dt!r}. Must be one of {sorted(_VALID_DEPLOYMENT_TYPES)}"
            )
        if self.max_rules < 1:
            raise ConfigValidationError("max_rules must be >= 1")
        if self.instance_count < 1:
            raise ConfigValidationError("instance_count must be >= 1")
        if self.region_count < 1:
            raise ConfigValidationError("region_count must be >= 1")

        # Logical consistency warnings
        if dt == "multi_region" and self.region_count < 2:
            warnings.append(
                "deployment_type is 'multi_region' but region_count < 2; "
                "consider setting region_count >= 2"
            )
        if dt == "multi_instance" and self.instance_count < 2:
            warnings.append(
                "deployment_type is 'multi_instance' but instance_count < 2; "
                "consider setting instance_count >= 2"
            )
        if self.expected_growth not in ("stable", "growing", "explosive"):
            warnings.append(
                f"expected_growth={self.expected_growth!r} not recognised; "
                "use 'stable', 'growing', or 'explosive'"
            )
        return warnings

    # File-based and dict-based configuration

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeploymentConfig:
        """Create a config from a plain dictionary.

        This is useful when you already loaded YAML / JSON yourself, or
        when you build the dict programmatically.

        Parameters
        ----------
        data : dict
            Configuration dictionary.  Supports nested ``requirements``
            and ``coordination`` sub-dicts as well as flat keys.
        """
        data = dict(data)  # shallow copy
        requirements = data.pop("requirements", {})
        coordination = data.pop("coordination", {})

        return cls(
            deployment_type=data.get("deployment_type", "single"),
            instance_count=data.get("instance_count", 1),
            region_count=data.get("region_count", 1),
            max_rules=data.get("max_rules", 50_000),
            expected_growth=data.get("expected_growth", "stable"),
            requires_sortable_ids=requirements.get(
                "sortable_ids", data.get("requires_sortable_ids", False)
            ),
            requires_deterministic=requirements.get(
                "deterministic", data.get("requires_deterministic", False)
            ),
            requires_human_readable=requirements.get(
                "human_readable", data.get("requires_human_readable", False)
            ),
            require_no_coordination=requirements.get(
                "no_coordination", data.get("require_no_coordination", False)
            ),
            storage_sensitive=data.get("storage_sensitive", False),
            latency_sensitive=data.get("latency_sensitive", False),
            machine_id=data.get("machine_id"),
            instance_id=data.get("instance_id"),
            redis_host=coordination.get("redis_host", data.get("redis_host", "localhost")),
            redis_port=coordination.get("redis_port", data.get("redis_port", 6379)),
            detected_from="dict",
        )

    @classmethod
    def from_file(cls, path: str | Path) -> DeploymentConfig:
        """Load configuration from a YAML or JSON file.

        Parameters
        ----------
        path : str | Path
            Path to ``fluxrules.yaml`` / ``fluxrules.json``.
        """
        path = str(path)
        with open(path) as fh:
            if path.endswith((".yaml", ".yml")):
                try:
                    import yaml  # type: ignore[import-untyped]

                    data = yaml.safe_load(fh) or {}
                except ImportError:
                    raise ImportError(
                        "PyYAML is required to load YAML config files. "
                        "Install it with: pip install pyyaml"
                    )
            else:
                data = json.load(fh)

        cfg = cls.from_dict(data)
        cfg.detected_from = "file"
        return cfg

    # Environment variables

    @classmethod
    def from_environment(cls) -> DeploymentConfig:
        """Build configuration from ``FLUXRULES_*`` environment variables."""

        def _int(var: str, default: int) -> int:
            try:
                return int(os.getenv(var, str(default)))
            except ValueError:
                logger.warning("Invalid %s, using default %d", var, default)
                return default

        def _bool(var: str) -> bool:
            return os.getenv(var, "false").lower() in ("true", "1", "yes")

        return cls(
            deployment_type=os.getenv("FLUXRULES_DEPLOYMENT_TYPE", "single"),
            instance_count=_int("FLUXRULES_INSTANCE_COUNT", 1),
            region_count=_int("FLUXRULES_REGION_COUNT", 1),
            max_rules=_int("FLUXRULES_MAX_RULES", 50_000),
            expected_growth=os.getenv("FLUXRULES_EXPECTED_GROWTH", "stable"),
            requires_sortable_ids=_bool("FLUXRULES_SORTABLE_IDS"),
            requires_deterministic=_bool("FLUXRULES_DETERMINISTIC"),
            requires_human_readable=_bool("FLUXRULES_HUMAN_READABLE"),
            require_no_coordination=_bool("FLUXRULES_NO_COORDINATION"),
            machine_id=(
                _int("FLUXRULES_MACHINE_ID", 0) if os.getenv("FLUXRULES_MACHINE_ID") else None
            ),
            instance_id=(
                _int("FLUXRULES_INSTANCE_ID", 0) if os.getenv("FLUXRULES_INSTANCE_ID") else None
            ),
            redis_host=os.getenv("FLUXRULES_REDIS_HOST", "localhost"),
            redis_port=_int("FLUXRULES_REDIS_PORT", 6379),
            detected_from="environment",
        )

    # Auto-detect with fallback chain

    @classmethod
    def load_with_fallback(cls) -> DeploymentConfig:
        """Load configuration using the fallback chain.

        1. ``FLUXRULES_CONFIG_FILE`` env → file
        2. Default file locations → file
        3. ``FLUXRULES_*`` env vars → environment
        4. Kubernetes detection (``HOSTNAME`` pattern)
        5. Sensible defaults
        """
        # Explicit config file path
        config_file = os.getenv("FLUXRULES_CONFIG_FILE")
        if config_file and os.path.isfile(config_file):
            logger.info("Loading configuration from file: %s", config_file)
            return cls.from_file(config_file)

        # Search default file locations
        default_locations = [
            Path("fluxrules.yaml"),
            Path("fluxrules.yml"),
            Path("fluxrules.json"),
            Path("config/fluxrules.yaml"),
            Path("config/fluxrules.yml"),
            Path("config/fluxrules.json"),
            Path.home() / ".fluxrules.yaml",
            Path("/etc/fluxrules/config.yaml"),
        ]
        for location in default_locations:
            if location.is_file():
                logger.info("Loading configuration from default location: %s", location)
                return cls.from_file(str(location))

        # Environment variables
        if os.getenv("FLUXRULES_DEPLOYMENT_TYPE") or os.getenv("FLUXRULES_MAX_RULES"):
            logger.info("Loading configuration from environment variables")
            return cls.from_environment()

        # Kubernetes auto-detect
        hostname = os.getenv("HOSTNAME", "")
        if hostname and "-" in hostname and hostname.rsplit("-", 1)[-1].isdigit():
            logger.info("Auto-detected Kubernetes StatefulSet from HOSTNAME=%s", hostname)
            return cls(
                deployment_type="multi_instance",
                instance_count=3,  # safe assumption for StatefulSet
                detected_from="kubernetes",
            )

        # Defaults
        logger.info("Using default configuration (single instance, sequential IDs)")
        return cls(detected_from="auto")

    # ── helpers ───────────────────────────────────────────────

    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"DeploymentConfig(detected_from={self.detected_from!r}, "
            f"type={self.deployment_type!r}, max_rules={self.max_rules:,}, "
            f"instances={self.instance_count}, regions={self.region_count})"
        )
