from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from typing import Optional
from datetime import datetime

class AuditService:
    def __init__(self, db: Session):
        self.db = db
    
    def log_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int],
        user_id: Optional[int],
        details: str,
        execution_time: Optional[float] = None,
        auto_commit: bool = True
    ):
        log = AuditLog(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            details=details,
            execution_time=execution_time
        )
        self.db.add(log)
        if auto_commit:
            self.db.commit()
