"""In-memory queue adapter for testing and embedded mode."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fluxrules.ports.queue import QueuePort


class InMemoryQueueAdapter(QueuePort):
    """In-memory queue implementation for testing and single-process mode.

    Thread-safe for single-process usage. Does not persist across restarts.
    """

    def __init__(self) -> None:
        self._topics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._offsets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._closed = False

    def enqueue(
        self,
        topic: str,
        partition_key: str,
        message: dict[str, Any],
        priority: int = 0,
    ) -> str:
        """Enqueue a message to a topic."""
        if self._closed:
            raise RuntimeError("Queue adapter is closed")

        message_id = str(uuid.uuid4())
        enriched = {
            "id": message_id,
            "type": message.get("type", "unknown"),
            "payload": message.get("payload", {}),
            "source": message.get("source", "api"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "priority": priority,
            "partition_key": partition_key,
            "retry_count": 0,
        }
        self._topics[topic].append(enriched)
        return message_id

    def dequeue(
        self,
        topic: str,
        consumer_group: str,
        timeout_ms: int = 1000,
    ) -> list[dict[str, Any]]:
        """Dequeue messages from a topic."""
        if self._closed:
            raise RuntimeError("Queue adapter is closed")

        current_offset = self._offsets[topic][consumer_group]
        messages = self._topics[topic][current_offset:]

        result = []
        for i, msg in enumerate(messages):
            result.append(
                {
                    "payload": msg,
                    "topic": topic,
                    "partition": 0,
                    "offset": current_offset + i,
                    "timestamp": msg["timestamp"],
                }
            )

        return result

    def commit_offset(self, topic: str, partition: int, offset: int, consumer_group: str) -> None:
        """Commit offset after successful processing."""
        self._offsets[topic][consumer_group] = offset + 1

    def peek(self, topic: str, partition: int, offset: int) -> dict[str, Any] | None:
        """Peek at a message without consuming."""
        messages = self._topics.get(topic, [])
        if 0 <= offset < len(messages):
            return messages[offset]
        return None

    def health_check(self) -> tuple[bool, str]:
        """Always healthy for in-memory."""
        if self._closed:
            return False, "Queue adapter is closed"
        return True, "In-memory queue is healthy"

    def close(self) -> None:
        """Mark as closed."""
        self._closed = True

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._topics.clear()
        self._offsets.clear()
        self._closed = False
