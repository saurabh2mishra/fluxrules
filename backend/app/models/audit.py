# backend/app/models/audit.py
"""Audit log model with optional HMAC-SHA256 integrity hashing.

When ``AUDIT_INTEGRITY_ENABLED`` is ``True`` (the default), each audit row
is stamped with a keyed hash so that post-hoc tampering can be detected
by re-computing and comparing hashes.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from datetime import datetime
from app.database import Base


class AuditLog(Base):
    """Immutable audit trail for all rule-engine operations.

    Rows in this table should **never** be updated or deleted through
    application code.  The ``integrity_hash`` column (when populated)
    allows offline verification that no row has been tampered with.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))
    details = Column(Text)
    execution_time = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    # HMAC-SHA256 integrity hash for tamper detection (nullable for
    # backward compatibility with rows created before this feature).
    integrity_hash = Column(String(64), nullable=True)