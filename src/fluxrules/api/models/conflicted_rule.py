from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fluxrules.api.database import Base


class ConflictedRule(Base):
    __tablename__ = "conflicted_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    group: Mapped[str | None] = mapped_column(String)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    condition_dsl: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rule_metadata: Mapped[str | None] = mapped_column(Text)

    # Conflict details
    conflict_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g. "priority_collision", "duplicate_condition"
    conflict_description: Mapped[str] = mapped_column(Text, nullable=False)
    conflicting_rule_id: Mapped[int | None] = mapped_column(
        Integer
    )  # ID of the existing rule it conflicts with
    conflicting_rule_name: Mapped[str | None] = mapped_column(String)

    # Who tried to create it
    submitted_by: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Review status: pending, approved, dismissed
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_notes: Mapped[str | None] = mapped_column(Text)

    new_rule_id: Mapped[int | None] = mapped_column(
        Integer
    )  # ID of the new/parked rule (if applicable)
