from prometheus_client import Counter, Histogram, CollectorRegistry

_registry = None
_events_processed = None
_rules_fired = None
_processing_time = None

# Simple counters for dashboard (in addition to Prometheus)
_dashboard_stats = {
    "events_processed": 0,
    "rules_fired": 0,
    "total_processing_time_ms": 0,
    "evaluation_count": 0
}

def get_metrics_registry():
    global _registry, _events_processed, _rules_fired, _processing_time
    
    if _registry is None:
        _registry = CollectorRegistry()
        
        _events_processed = Counter(
            "events_processed_total",
            "Total number of events processed",
            registry=_registry
        )
        
        _rules_fired = Counter(
            "rules_fired_total",
            "Total number of rules fired",
            registry=_registry
        )
        
        _processing_time = Histogram(
            "event_processing_seconds",
            "Time spent processing events",
            registry=_registry
        )
    
    return _registry

def increment_events_processed():
    global _events_processed, _dashboard_stats
    if _events_processed:
        _events_processed.inc()
    _dashboard_stats["events_processed"] += 1

def increment_rules_fired(count: int = 1):
    global _rules_fired, _dashboard_stats
    if _rules_fired:
        _rules_fired.inc(count)
    _dashboard_stats["rules_fired"] += count

def observe_processing_time(duration_seconds: float):
    global _processing_time, _dashboard_stats
    if _processing_time:
        _processing_time.observe(duration_seconds)
    _dashboard_stats["total_processing_time_ms"] += duration_seconds * 1000
    _dashboard_stats["evaluation_count"] += 1

def get_dashboard_metrics() -> dict:
    """Get human-friendly metrics for dashboard."""
    avg_time = 0
    if _dashboard_stats["evaluation_count"] > 0:
        avg_time = _dashboard_stats["total_processing_time_ms"] / _dashboard_stats["evaluation_count"]
    
    return {
        "events_processed": _dashboard_stats["events_processed"],
        "rules_fired": _dashboard_stats["rules_fired"],
        "avg_processing_time_ms": round(avg_time, 2),
        "total_evaluations": _dashboard_stats["evaluation_count"]
    }
