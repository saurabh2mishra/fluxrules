# backend/app/models/audit.py
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from datetime import datetime
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))
    details = Column(Text)
    execution_time = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)