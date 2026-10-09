from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fluxrules.api.database import Base

if TYPE_CHECKING:
    from fluxrules.api.models.user import User


class Rule(Base):
    __tablename__ = "rules"

    __table_args__ = (
        Index("ix_rules_group_priority", "group", "priority"),
        Index("ix_rules_enabled_group", "enabled", "group"),
        Index("uq_rules_group_id_name", "group", "id", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    group: Mapped[str | None] = mapped_column(String, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    condition_dsl: Mapped[Any] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rule_metadata: Mapped[Any] = mapped_column(JSON, nullable=True)
    evaluation_mode: Mapped[str | None] = mapped_column(String, nullable=True, default="stateless")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    versions: Mapped[list["RuleVersion"]] = relationship(
        "RuleVersion", back_populates="rule", cascade="all, delete-orphan"
    )
    creator: Mapped[Optional["User"]] = relationship("User", back_populates="rules")


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rule_id: Mapped[int] = mapped_column(Integer, ForeignKey("rules.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    group: Mapped[str | None] = mapped_column(String)
    priority: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool | None] = mapped_column(Boolean)
    condition_dsl: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rule_metadata: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    rule: Mapped["Rule"] = relationship("Rule", back_populates="versions")
    creator: Mapped[Optional["User"]] = relationship("User")
