"""Port interface for health checking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class HealthCheckPort(ABC):
    """Abstract interface for health checking.

    Implementations check connectivity and status of all system components.
    """

    @abstractmethod
    def check_queue(self) -> tuple[bool, str]:
        """Check if queue system is healthy."""
        ...

    @abstractmethod
    def check_cache(self) -> tuple[bool, str]:
        """Check if cache is accessible."""
        ...

    @abstractmethod
    def check_persistence(self) -> tuple[bool, str]:
        """Check if persistence layer is healthy."""
        ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return overall system health status."""
        ...
