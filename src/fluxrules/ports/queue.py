"""Port interface for message queue (fact distribution)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QueuePort(ABC):
    """Abstract interface for message queue - for fact distribution.

    Implementations may include Kafka, RabbitMQ, or in-memory queues.
    All implementations must:
    - Handle concurrent calls safely
    - Return unique message IDs on enqueue
    - Support consumer groups for offset management
    - Provide health check capabilities
    """

    @abstractmethod
    def enqueue(
        self,
        topic: str,
        partition_key: str,
        message: dict[str, Any],
        priority: int = 0,
    ) -> str:
        """Enqueue a message to a topic.

        Args:
            topic: Target topic (e.g., "facts", "commands", "metrics")
            partition_key: Routing key for partition assignment
            message: Message payload with type, payload, timestamp, source
            priority: 0-9 (higher = process first)

        Returns:
            Unique message_id for tracking
        """
        ...

    @abstractmethod
    def dequeue(
        self,
        topic: str,
        consumer_group: str,
        timeout_ms: int = 1000,
    ) -> list[dict[str, Any]]:
        """Dequeue messages from a topic.

        Args:
            topic: Which topic to consume from
            consumer_group: Consumer group for offset management
            timeout_ms: How long to wait for messages

        Returns:
            List of messages with metadata (offset, partition, timestamp)
        """
        ...

    @abstractmethod
    def commit_offset(self, topic: str, partition: int, offset: int, consumer_group: str) -> None:
        """Commit offset after successful processing."""
        ...

    @abstractmethod
    def peek(self, topic: str, partition: int, offset: int) -> dict[str, Any] | None:
        """Peek at a message without consuming (for debugging)."""
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check queue system health."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Graceful shutdown."""
        ...
