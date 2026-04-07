from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AnalyticsStore(ABC):
    @abstractmethod
    def increment_event(self, duration_ms: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def increment_rule(self, rule_id: str, execution_time_ms: float, timestamp: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_explanation(self, entry: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_stats(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def read_rule_metrics(self) -> Dict[str, Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def read_explanations(self, rule_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        raise NotImplementedError


class InMemoryAnalyticsStore(AnalyticsStore):
    def __init__(self, max_explanations: int = 1000):
        self._lock = threading.RLock()
        self._max_explanations = max_explanations
        self._stats = {
            "events_processed": 0,
            "rules_fired": 0,
            "total_processing_time_ms": 0.0,
            "evaluation_count": 0,
        }
        self._rule_metrics: Dict[str, Dict[str, Any]] = {}
        self._explanations: List[Dict[str, Any]] = []

    def increment_event(self, duration_ms: float) -> None:
        with self._lock:
            self._stats["events_processed"] += 1
            self._stats["total_processing_time_ms"] += duration_ms
            self._stats["evaluation_count"] += 1

    def increment_rule(self, rule_id: str, execution_time_ms: float, timestamp: str) -> None:
        with self._lock:
            metric = self._rule_metrics.setdefault(
                rule_id,
                {
                    "rule_id": rule_id,
                    "hit_count": 0,
                    "total_execution_time_ms": 0.0,
                    "last_fired_at": None,
                },
            )
            metric["hit_count"] += 1
            metric["total_execution_time_ms"] += execution_time_ms
            metric["last_fired_at"] = timestamp
            self._stats["rules_fired"] += 1

    def add_explanation(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._explanations.append(entry)
            if len(self._explanations) > self._max_explanations:
                self._explanations = self._explanations[-self._max_explanations :]

    def read_stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def read_rule_metrics(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._rule_metrics.items()}

    def read_explanations(self, rule_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._explanations
            if rule_id is not None:
                items = [e for e in items if str(e.get("rule_id")) == str(rule_id)]
            return [dict(e) for e in items[-limit:]][::-1]


class RedisAnalyticsStore(AnalyticsStore):
    STATS_KEY = "analytics:stats"
    RULES_KEY = "analytics:rules"
    EXPLANATIONS_KEY = "analytics:explanations"

    def __init__(self, redis_client, max_explanations: int = 1000):
        self.redis = redis_client
        self.max_explanations = max_explanations

    def increment_event(self, duration_ms: float) -> None:
        self.redis.hincrby(self.STATS_KEY, "events_processed", 1)
        self.redis.hincrbyfloat(self.STATS_KEY, "total_processing_time_ms", duration_ms)
        self.redis.hincrby(self.STATS_KEY, "evaluation_count", 1)

    def increment_rule(self, rule_id: str, execution_time_ms: float, timestamp: str) -> None:
        raw = self.redis.hget(self.RULES_KEY, rule_id)
        if raw:
            data = json.loads(raw)
        else:
            data = {
                "rule_id": rule_id,
                "hit_count": 0,
                "total_execution_time_ms": 0.0,
                "last_fired_at": None,
            }
        data["hit_count"] += 1
        data["total_execution_time_ms"] += execution_time_ms
        data["last_fired_at"] = timestamp
        self.redis.hset(self.RULES_KEY, rule_id, json.dumps(data))
        self.redis.hincrby(self.STATS_KEY, "rules_fired", 1)

    def add_explanation(self, entry: Dict[str, Any]) -> None:
        self.redis.rpush(self.EXPLANATIONS_KEY, json.dumps(entry))
        self.redis.ltrim(self.EXPLANATIONS_KEY, -self.max_explanations, -1)

    def read_stats(self) -> Dict[str, Any]:
        raw = self.redis.hgetall(self.STATS_KEY) or {}
        return {
            "events_processed": int(raw.get("events_processed", 0)),
            "rules_fired": int(raw.get("rules_fired", 0)),
            "total_processing_time_ms": float(raw.get("total_processing_time_ms", 0.0)),
            "evaluation_count": int(raw.get("evaluation_count", 0)),
        }

    def read_rule_metrics(self) -> Dict[str, Dict[str, Any]]:
        raw = self.redis.hgetall(self.RULES_KEY) or {}
        out: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            parsed = json.loads(value)
            out[str(key)] = parsed
        return out

    def read_explanations(self, rule_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        raw = self.redis.lrange(self.EXPLANATIONS_KEY, -limit, -1)
        items = [json.loads(x) for x in raw]
        if rule_id is not None:
            items = [e for e in items if str(e.get("rule_id")) == str(rule_id)]
        return items[::-1]
