from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime
from app.database import Base


class ConflictedRule(Base):
    __tablename__ = "conflicted_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    group = Column(String)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    condition_dsl = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    rule_metadata = Column(Text)

    # Conflict details
    conflict_type = Column(String, nullable=False)  # e.g. "priority_collision", "duplicate_condition"
    conflict_description = Column(Text, nullable=False)
    conflicting_rule_id = Column(Integer)  # ID of the existing rule it conflicts with
    conflicting_rule_name = Column(String)

    # Who tried to create it
    submitted_by = Column(Integer)
    submitted_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Review status: pending, approved, dismissed
    status = Column(String, default="pending", index=True)
    reviewed_by = Column(Integer)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)

    new_rule_id = Column(Integer)  # ID of the new/parked rule (if applicable)
