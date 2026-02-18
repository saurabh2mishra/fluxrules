import json
import time
from app.database import SessionLocal
from app.utils.redis_client import get_redis_client
from app.engine.rete_engine import ReteEngine
from app.services.audit_service import AuditService
from app.utils.metrics import increment_events_processed, increment_rules_fired, observe_processing_time

def process_events():
    redis_client = get_redis_client()
    db = SessionLocal()
    
    try:
        while True:
            _, event_data = redis_client.brpop("event_queue", timeout=1)
            if not event_data:
                continue
            
            start_time = time.time()
            event = json.loads(event_data)
            
            engine = ReteEngine(db)
            result = engine.simulate(event["data"])
            
            audit_service = AuditService(db)
            for matched_rule in result["matched_rules"]:
                audit_service.log_action(
                    "rule_fired",
                    "rule",
                    matched_rule["id"],
                    event.get("user_id"),
                    f"Rule fired for event {event['event_id']}"
                )
                increment_rules_fired()
            
            processing_time = time.time() - start_time
            observe_processing_time(processing_time)
            increment_events_processed()
            
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