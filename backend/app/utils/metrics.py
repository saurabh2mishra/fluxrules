from prometheus_client import Counter, Histogram, CollectorRegistry

_registry = None
_events_processed = None
_rules_fired = None
_processing_time = None

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
    global _events_processed
    if _events_processed:
        _events_processed.inc()

def increment_rules_fired():
    global _rules_fired
    if _rules_fired:
        _rules_fired.inc()

def observe_processing_time(duration):
    global _processing_time
    if _processing_time:
        _processing_time.observe(duration)
