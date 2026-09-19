"""Unified Rule ID Generator with strategy pattern and auto-detection.

This module provides a single entry point (``RuleIDGenerator``) for all
rule-ID generation in FluxRules.  Users never instantiate individual
strategy classes directly; instead they obtain a ``RuleIDGenerator``
via the factory or let the engine create one automatically.

Strategies:
    * **Sequential** - simple counter (default, single-instance)
    * **HashBased** - deterministic hash of rule content
    * **Snowflake** - distributed, time-sortable (Twitter Snowflake-like)
    * **UUID** - globally unique, zero coordination
    * **Hybrid** - local cache + central coordination

Usage::

    # Auto-detect (zero config)
    gen = RuleIDGenerator()
    rule_id = gen.next_id()

    # Explicit strategy
    gen = RuleIDGenerator(strategy="snowflake", machine_id=1)

    # From DeploymentConfig
    from fluxrules.config.deployment import DeploymentConfig
    config = DeploymentConfig(deployment_type="multi_region", max_rules=500_000)
    gen = RuleIDGenerator.from_config(config)
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# Strategy enum


class IDStrategy(Enum):
    """Available ID generation strategies."""

    SEQUENTIAL = "sequential"
    HASH_BASED = "hash_based"
    SNOWFLAKE = "snowflake"
    UUID = "uuid"
    HYBRID = "hybrid"


# Internal strategy implementations (private)


class _SequentialStrategy:
    """Thread-safe sequential counter."""

    def __init__(self, start: int = 1) -> None:
        self._counter = start - 1
        self._lock = threading.Lock()

    def next_id(self, **_kwargs: Any) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def reset(self, start: int = 1) -> None:
        with self._lock:
            self._counter = start - 1


class _HashBasedStrategy:
    """Deterministic hash of rule content → int ID."""

    def next_id(self, *, name: str = "", content: str = "", **_kwargs: Any) -> int:
        raw = f"{name}:{content}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return int(digest[:15], 16)  # 60-bit positive int

    def reset(self, start: int = 1) -> None:
        pass  # stateless


class _SnowflakeStrategy:
    """Twitter Snowflake-inspired 64-bit ID generator.

    Layout (64 bits):
        1 bit unused | 41 bits timestamp | 10 bits machine | 12 bits sequence
    """

    EPOCH = 1_700_000_000_000  # custom epoch (2023-11-14)
    MACHINE_BITS = 10
    SEQUENCE_BITS = 12
    MAX_MACHINE = (1 << MACHINE_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

    def __init__(self, machine_id: int = 0) -> None:
        if not 0 <= machine_id <= self.MAX_MACHINE:
            raise ValueError(f"machine_id must be 0..{self.MAX_MACHINE}")
        self._machine_id = machine_id
        self._sequence = 0
        self._last_ts = -1
        self._lock = threading.Lock()

    def _current_ms(self) -> int:
        return int(time.time() * 1000)

    def next_id(self, **_kwargs: Any) -> int:
        with self._lock:
            ts = self._current_ms() - self.EPOCH
            if ts == self._last_ts:
                self._sequence = (self._sequence + 1) & self.MAX_SEQUENCE
                if self._sequence == 0:
                    # wait for next millisecond
                    while ts <= self._last_ts:
                        ts = self._current_ms() - self.EPOCH
            else:
                self._sequence = 0
            self._last_ts = ts
            return (
                (ts << (self.MACHINE_BITS + self.SEQUENCE_BITS))
                | (self._machine_id << self.SEQUENCE_BITS)
                | self._sequence
            )

    def reset(self, start: int = 1) -> None:
        with self._lock:
            self._sequence = 0
            self._last_ts = -1


class _UUIDStrategy:
    """UUID v4 string IDs."""

    def next_id(self, **_kwargs: Any) -> str:
        return str(uuid.uuid4())

    def reset(self, start: int = 1) -> None:
        pass  # stateless


class _HybridStrategy:
    """Local sequential + global prefix for multi-instance isolation.

    Each instance gets a unique prefix derived from *instance_id* so
    IDs never collide across instances, yet remain sortable within an
    instance.
    """

    def __init__(self, instance_id: int = 0) -> None:
        self._instance_id = instance_id
        self._seq = _SequentialStrategy()

    def next_id(self, **_kwargs: Any) -> int:
        local = self._seq.next_id()
        # Pack: upper 16 bits = instance, lower 48 bits = local seq
        return (self._instance_id << 48) | local

    def reset(self, start: int = 1) -> None:
        self._seq.reset(start)


# Unified public class

_Strategy = (
    _SequentialStrategy | _HashBasedStrategy | _SnowflakeStrategy | _UUIDStrategy | _HybridStrategy
)


class RuleIDGenerator:
    """Single entry-point for all rule-ID generation in FluxRules.

    Parameters
    ----------
    strategy : str | IDStrategy, optional
        Which generation strategy to use.  Defaults to ``"sequential"``.
    machine_id : int, optional
        Machine identifier for Snowflake / Hybrid strategies.
    instance_id : int, optional
        Instance identifier for Hybrid strategy.
    start : int, optional
        Starting value for Sequential strategy (default ``1``).

    Examples
    --------
    >>> gen = RuleIDGenerator()                       # Sequential (default)
    >>> gen.next_id()
    1
    >>> gen = RuleIDGenerator(strategy="uuid")        # UUID
    >>> isinstance(gen.next_id(), str)
    True
    >>> gen = RuleIDGenerator(strategy="snowflake", machine_id=1)
    >>> isinstance(gen.next_id(), int)
    True
    """

    def __init__(
        self,
        strategy: str | IDStrategy = IDStrategy.SEQUENTIAL,
        *,
        machine_id: int = 0,
        instance_id: int = 0,
        start: int = 1,
    ) -> None:
        if isinstance(strategy, str):
            strategy = IDStrategy(strategy)
        self._strategy_enum = strategy
        self._impl: _Strategy = self._build_strategy(
            strategy,
            machine_id=machine_id,
            instance_id=instance_id,
            start=start,
        )
        logger.debug("RuleIDGenerator created with strategy=%s", self._strategy_enum.value)

    # ── factory helpers ──────────────────────────────────────

    @classmethod
    def from_config(cls, config: Any) -> RuleIDGenerator:
        """Create a generator auto-detected from a ``DeploymentConfig``.

        Parameters
        ----------
        config : DeploymentConfig
            Deployment configuration object.

        Returns
        -------
        RuleIDGenerator
            Optimally configured generator.
        """
        strategy = _auto_detect_strategy(config)
        machine_id = getattr(config, "machine_id", None) or _detect_machine_id()
        instance_id = getattr(config, "instance_id", None) or 0
        logger.info(
            "Auto-detected ID strategy=%s for deployment_type=%s, max_rules=%s",
            strategy.value,
            getattr(config, "deployment_type", "unknown"),
            getattr(config, "max_rules", "unknown"),
        )
        return cls(
            strategy=strategy,
            machine_id=machine_id,
            instance_id=instance_id,
        )

    @classmethod
    def auto_detect(cls) -> RuleIDGenerator:
        """Create a generator by auto-detecting the deployment context.

        Follows the fallback chain:
        1. ``FLUXRULES_CONFIG_FILE`` → YAML/JSON
        2. ``FLUXRULES_*`` env vars
        3. Kubernetes detection
        4. Sensible defaults (Sequential)

        Returns
        -------
        RuleIDGenerator
        """
        from fluxrules.config.deployment import DeploymentConfig

        config = DeploymentConfig.load_with_fallback()
        return cls.from_config(config)

    # ── public API ───────────────────────────────────────────

    @property
    def strategy(self) -> IDStrategy:
        """Currently active strategy."""
        return self._strategy_enum

    def next_id(self, *, name: str = "", content: str = "") -> int | str:
        """Generate the next unique rule ID.

        Parameters
        ----------
        name : str, optional
            Rule name (used by HashBased strategy).
        content : str, optional
            Rule content hash input (used by HashBased strategy).

        Returns
        -------
        int | str
            Unique ID (int for most strategies, str for UUID).
        """
        return self._impl.next_id(name=name, content=content)

    def reset(self, start: int = 1) -> None:
        """Reset generator state (mainly for testing)."""
        self._impl.reset(start)

    def __repr__(self) -> str:
        return f"RuleIDGenerator(strategy={self._strategy_enum.value!r})"

    # ── internals ────────────────────────────────────────────

    @staticmethod
    def _build_strategy(
        strategy: IDStrategy,
        *,
        machine_id: int = 0,
        instance_id: int = 0,
        start: int = 1,
    ) -> _Strategy:
        if strategy is IDStrategy.SEQUENTIAL:
            return _SequentialStrategy(start=start)
        if strategy is IDStrategy.HASH_BASED:
            return _HashBasedStrategy()
        if strategy is IDStrategy.SNOWFLAKE:
            return _SnowflakeStrategy(machine_id=machine_id)
        if strategy is IDStrategy.UUID:
            return _UUIDStrategy()
        if strategy is IDStrategy.HYBRID:
            return _HybridStrategy(instance_id=instance_id)
        raise ValueError(f"Unknown strategy: {strategy}")


# Auto-detection logic


def _detect_machine_id() -> int:
    """Best-effort machine ID from environment."""
    env_id = os.getenv("MACHINE_ID") or os.getenv("FLUXRULES_MACHINE_ID")
    if env_id is not None:
        return int(env_id) % 1023

    hostname = os.getenv("HOSTNAME", "")
    if "-" in hostname:
        last = hostname.rsplit("-", 1)[-1]
        if last.isdigit():
            return int(last) % 1023

    return int(hashlib.md5(hostname.encode(), usedforsecurity=False).hexdigest(), 16) % 1023


def _auto_detect_strategy(config: Any) -> IDStrategy:
    """Select optimal strategy from a DeploymentConfig-like object."""
    deployment_type = str(getattr(config, "deployment_type", "single"))
    max_rules: int = getattr(config, "max_rules", 50_000)
    requires_sortable = getattr(config, "requires_sortable_ids", False)
    requires_deterministic = getattr(config, "requires_deterministic", False)
    no_coordination = getattr(config, "require_no_coordination", False)

    # Hard constraint: no coordination in distributed
    if no_coordination and deployment_type not in ("single", "single_instance"):
        return IDStrategy.UUID if max_rules > 100_000 else IDStrategy.HASH_BASED

    # Multi-region MUST use distributed-safe
    if deployment_type in ("multi_region",):
        return (
            IDStrategy.SNOWFLAKE if (requires_sortable or max_rules > 10_000) else IDStrategy.UUID
        )

    # Multi-instance same DC
    if deployment_type in ("multi_instance",):
        if max_rules > 100_000:
            return IDStrategy.SNOWFLAKE
        return IDStrategy.HYBRID

    # Serverless
    if deployment_type in ("serverless",):
        return IDStrategy.UUID

    # Single instance
    if requires_deterministic:
        return IDStrategy.HASH_BASED

    # Scale check for single instance
    if max_rules > 1_000_000:
        return IDStrategy.SNOWFLAKE

    return IDStrategy.SEQUENTIAL
