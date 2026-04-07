import json
import time
from app.database import SessionLocal
from app.utils.redis_client import get_redis_client
from app.engine.rete_engine import ReteEngine
from app.services.audit_service import AuditService
from app.utils.metrics import increment_events_processed, increment_rules_fired, observe_processing_time
from app.services.analytics_service import get_analytics_service

def process_events():
    redis_client = get_redis_client()
    db = SessionLocal()
    
    analytics_service = get_analytics_service()

    try:
        while True:
            if redis_client is None:
                time.sleep(1)
                continue

            _, event_data = redis_client.brpop("event_queue", timeout=1)
            if not event_data:
                continue
            
            start_time = time.time()
            event = json.loads(event_data)
            
            engine = ReteEngine(db)
            result = engine.simulate(event["data"])
            
            audit_service = AuditService(db)
            per_rule_ms = ((time.time() - start_time) * 1000 / max(len(result["matched_rules"]), 1))
            explanations = result.get("explanations", {})

            for matched_rule in result["matched_rules"]:
                audit_service.log_action(
                    "rule_fired",
                    "rule",
                    matched_rule["id"],
                    event.get("user_id"),
                    f"Rule fired for event {event['event_id']}"
                )
                increment_rules_fired()
                analytics_service.record_rule_execution(
                    str(matched_rule["id"]),
                    per_rule_ms,
                    event.get("data", {}),
                    explanation=explanations.get(matched_rule["id"]) or explanations.get(str(matched_rule["id"])),
                )
            
            processing_time = time.time() - start_time
            observe_processing_time(processing_time)
            increment_events_processed()
            analytics_service.record_event_processed(processing_time * 1000)
            
            audit_service.log_action(
                "event_processed",
                "event",
                None,
                event.get("user_id"),
                f"Event {event['event_id']} processed",
                processing_time
            )
            
    except KeyboardInterrupt:
        print("Worker stopped")
    finally:
        db.close()

if __name__ == "__main__":
    process_events()