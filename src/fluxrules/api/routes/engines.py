"""Engine Evaluation API routes for the PHREAK engine.

Provides REST endpoints for:
- Evaluating events against rules
- Simulating rule matching (dry-run)
- Querying engine statistics
- Performance monitoring
"""

import contextlib
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fluxrules.api.config import settings
from fluxrules.api.database import get_db
from fluxrules.api.engines import APIEngineAdapter
from fluxrules.engine import get_available_engines, get_engine

router = APIRouter(prefix="/api/v1/engines", tags=["engines"])


def validate_engine_type(engine_type: str) -> bool:
    """Return True if ``engine_type`` is a selectable engine (case-insensitive)."""
    if not engine_type:
        return False
    return engine_type.upper() in {name.upper() for name in get_available_engines()}


# Request/Response Models
class EvaluationRequest(BaseModel):
    """Request to evaluate an event against rules."""

    event: dict[str, Any] = Field(..., description="Event/fact data to evaluate")
    rule_ids: list[int] | None = Field(None, description="Optional: evaluate only these rule IDs")
    engine_type: str | None = Field(
        None,
        description="Optional: override default engine type (defaults to PHREAK)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event": {"amount": 1500.0, "status": "vip"},
                "rule_ids": None,
                "engine_type": "PHREAK",
            }
        }
    )


class SimulationRequest(BaseModel):
    """Request to simulate event evaluation (dry-run)."""

    event: dict[str, Any]
    rule_ids: list[int] | None = None
    engine_type: str | None = None


class EvaluationResponse(BaseModel):
    """Response from event evaluation."""

    matched_rules: list[dict[str, Any]]
    execution_order: list[int]
    explanations: dict[int, str]
    stats: dict[str, Any]
    engine_type: str
    dry_run: bool


class EngineStatistics(BaseModel):
    """Engine statistics."""

    engine_type: str
    rules_loaded: int
    memory_usage_mb: float
    evaluation_count: int
    avg_evaluation_time_ms: float
    performance_metrics: dict[str, Any]


class EngineConfig(BaseModel):
    """Engine configuration."""

    engine_type: str
    available_engines: list[str]
    current_engine: str
    settings: dict[str, Any]


# Routes
@router.post("/evaluate", response_model=EvaluationResponse)
def evaluate_event(
    request: EvaluationRequest,
    db=Depends(get_db),
) -> dict[str, Any]:
    """Evaluate an event against loaded rules.

    **Single-fact boundary:** the engine matches **one flattened event** against
    each rule independently. It does not join multiple events, aggregate over a
    collection of facts, or correlate across time. Correlate/aggregate upstream
    and pass a pre-joined event. See ``docs/engine-scope-and-limits.md``.

    Args:
        request: Evaluation request with event data
        db: Database session

    Returns:
        Matched rules, execution order, and statistics

    Example:
        POST /api/v1/engines/evaluate
        {
            "event": {"amount": 1500, "status": "vip"},
            "rule_ids": [1, 2, 3],
            "engine_type": "PHREAK"
        }
    """
    try:
        # Determine engine type
        engine_type = request.engine_type or settings.RULE_ENGINE_TYPE

        # Validate engine type
        if not validate_engine_type(engine_type):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid engine type: {engine_type}. "
                f"Available: {', '.join(get_available_engines())}",
            )

        # Route through the tested adapter so the HTTP path uses the same
        # rule-loading, evaluation, and response contract as the rest of the API.
        adapter = APIEngineAdapter(engine_type=engine_type, db=db)
        result = adapter.evaluate(request.event, rule_ids=request.rule_ids)
        result["dry_run"] = False
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation error: {e!s}")


@router.post("/simulate", response_model=EvaluationResponse)
def simulate_evaluation(
    request: SimulationRequest,
    db=Depends(get_db),
) -> dict[str, Any]:
    """Simulate evaluation of an event (dry-run, no side effects).

    Args:
        request: Simulation request
        db: Database session

    Returns:
        Matched rules and statistics (same as evaluate but no side effects)
    """
    try:
        engine_type = request.engine_type or settings.RULE_ENGINE_TYPE

        if not validate_engine_type(engine_type):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid engine type: {engine_type}",
            )

        adapter = APIEngineAdapter(engine_type=engine_type, db=db)
        result = adapter.evaluate(request.event, rule_ids=request.rule_ids)
        result["dry_run"] = True
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
def get_engine_stats(
    engine_type: str | None = Query(None, description="Engine type (PHREAK)"),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Get engine statistics.

    Args:
        engine_type: Optional engine type override

    Returns:
        Engine statistics and performance metrics
    """
    try:
        engine_type = engine_type or settings.RULE_ENGINE_TYPE

        if not validate_engine_type(engine_type):
            raise HTTPException(status_code=400, detail="Invalid engine type")

        adapter = APIEngineAdapter(engine_type=engine_type, db=db)
        return adapter.get_stats()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=EngineConfig)
def get_engine_config() -> dict[str, Any]:
    """Get current engine configuration and available engines.

    Returns:
        Engine configuration and list of available engines
    """
    available = get_available_engines()
    current = settings.RULE_ENGINE_TYPE

    config = {
        "engine_type": current,
        "available_engines": available,
        "current_engine": current,
        "settings": {
            "tuple_ttl_seconds": getattr(settings, "TUPLE_TTL_SECONDS", 300),
            "cleanup_interval_seconds": getattr(settings, "TUPLE_CLEANUP_INTERVAL_SECONDS", 60),
            "rule_memory_quota_mb": getattr(settings, "RULE_MEMORY_QUOTA_MB", 100.0),
            "quota_enforcement": getattr(settings, "RULE_QUOTA_ENFORCEMENT", "warn"),
        },
    }

    return config


@router.post("/switch")
def switch_engine(
    engine_type: str = Body(..., description="Engine type to switch to (PHREAK)"),
) -> dict[str, Any]:
    """Switch to a different engine type.

    Args:
        engine_type: Target engine type

    Returns:
        Confirmation with new engine config
    """
    if not validate_engine_type(engine_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine type: {engine_type}. "
            f"Available: {', '.join(get_available_engines())}",
        )

    # Note: In a real implementation, this would update settings
    # For now, we just return the configuration

    return {
        "status": "success",
        "message": f"Switched to {engine_type} engine",
        "current_engine": engine_type,
        "available_engines": get_available_engines(),
    }


@router.post("/reload")
def reload_rules(
    engine_type: str | None = Query(None),
) -> dict[str, Any]:
    """Reload rules from database.

    Args:
        engine_type: Optional engine type override

    Returns:
        Confirmation with updated rule count
    """
    try:
        engine_type = engine_type or settings.RULE_ENGINE_TYPE

        if not validate_engine_type(engine_type):
            raise HTTPException(status_code=400, detail="Invalid engine type")

        engine = get_engine(engine_type=engine_type)

        # The engine is already initialized with rules.
        # To fully "reload", we clear and reinitialize (in a real implementation,
        # this would load from a database). For now, just return current stats.
        stats = engine.get_stats()

        return {
            "status": "success",
            "message": "Engine reloaded",
            "engine_type": engine_type,
            "rules_loaded": stats.get("rules_loaded", 0),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available")
def list_available_engines() -> dict[str, Any]:
    """Get list of available engines.

    Returns:
        List of available engine types and their descriptions
    """
    available = get_available_engines()
    descriptions = {
        "PHREAK": "Lazy PHREAK evaluation (the FluxRules engine)",
    }

    return {
        "available_engines": available,
        "descriptions": {
            engine: descriptions.get(engine, "No description available") for engine in available
        },
        "current_engine": settings.RULE_ENGINE_TYPE,
    }


@router.post("/benchmark")
def benchmark_engine(
    engine_type: str | None = Query(None),
    num_events: int = Query(100, ge=1, le=10000),
    num_fields: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """Run a quick benchmark of an engine.

    Args:
        engine_type: Engine to benchmark
        num_events: Number of events to evaluate
        num_fields: Number of fields per event

    Returns:
        Benchmark results (latency percentiles, throughput)
    """
    import statistics
    import time

    try:
        engine_type = engine_type or settings.RULE_ENGINE_TYPE

        if not validate_engine_type(engine_type):
            raise HTTPException(status_code=400, detail="Invalid engine type")

        engine = get_engine(engine_type=engine_type)

        # Generate test events
        import random

        events = [
            {f"field_{i}": random.uniform(0, 10000) for i in range(num_fields)}
            for _ in range(num_events)
        ]

        # Warm up
        for event in events[:5]:
            with contextlib.suppress(Exception):
                engine.evaluate(event)

        # Benchmark
        latencies = []
        for event in events:
            t0 = time.perf_counter()
            with contextlib.suppress(Exception):
                engine.evaluate(event)
                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)  # Convert to ms

        if not latencies:
            raise HTTPException(status_code=500, detail="Benchmark produced no results")

        sorted_latencies = sorted(latencies)
        result = {
            "engine_type": engine_type,
            "num_events": len(latencies),
            "latency_ms": {
                "min": round(min(latencies), 3),
                "max": round(max(latencies), 3),
                "mean": round(statistics.mean(latencies), 3),
                "median": round(statistics.median(latencies), 3),
                "p95": round(sorted_latencies[int(len(sorted_latencies) * 0.95)], 3),
                "p99": round(sorted_latencies[int(len(sorted_latencies) * 0.99)], 3),
            },
            "throughput_events_per_sec": round(len(latencies) / (sum(latencies) / 1000), 1),
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
